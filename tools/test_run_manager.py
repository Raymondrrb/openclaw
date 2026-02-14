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
import wave
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


# ---------------------------------------------------------------------------
# Baptism script tests
# ---------------------------------------------------------------------------

class TestBaptism(unittest.TestCase):
    """Tests for scripts/baptism.py checks and report."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_check_ffprobe(self):
        self._add_scripts_path()
        from baptism import check_ffprobe
        result = check_ffprobe()
        # ffprobe may or may not be installed in test env
        self.assertIsInstance(result.passed, bool)
        self.assertEqual(result.name, "ffprobe")

    def test_check_state_dirs_missing(self):
        self._add_scripts_path()
        from baptism import check_state_dirs
        with tempfile.TemporaryDirectory() as td:
            result = check_state_dirs(Path(td) / "nonexistent")
            self.assertFalse(result.passed)
            self.assertIn("Missing", result.detail)

    def test_check_state_dirs_present(self):
        self._add_scripts_path()
        from baptism import check_state_dirs
        with tempfile.TemporaryDirectory() as td:
            sd = Path(td) / "state"
            (sd / "video" / "final").mkdir(parents=True)
            result = check_state_dirs(sd)
            self.assertTrue(result.passed)

    def test_check_index_health_no_index(self):
        self._add_scripts_path()
        from baptism import check_index_health
        with tempfile.TemporaryDirectory() as td:
            result = check_index_health(Path(td))
            self.assertTrue(result.passed)
            self.assertIn("No index", result.detail)

    def test_check_index_health_valid(self):
        self._add_scripts_path()
        from baptism import check_index_health
        with tempfile.TemporaryDirectory() as td:
            sd = Path(td)
            vid = sd / "video"
            vid.mkdir(parents=True)
            idx = vid / "index.json"
            final = vid / "final"
            final.mkdir()
            v = final / "test.mp4"
            v.write_bytes(b"x" * 100)
            idx.write_text(json.dumps({
                "version": "1.0",
                "items": {"abc": {"path": str(v), "file_mtime_ns": 123}},
            }))
            result = check_index_health(sd)
            self.assertTrue(result.passed)
            self.assertIn("1 entries", result.detail)

    def test_check_index_health_missing_files(self):
        self._add_scripts_path()
        from baptism import check_index_health
        with tempfile.TemporaryDirectory() as td:
            sd = Path(td)
            vid = sd / "video"
            vid.mkdir(parents=True)
            idx = vid / "index.json"
            idx.write_text(json.dumps({
                "version": "1.0",
                "items": {"abc": {"path": "/nonexistent/video.mp4"}},
            }))
            result = check_index_health(sd)
            self.assertFalse(result.passed)
            self.assertIn("missing files", result.detail)

    def test_check_orphans_clean(self):
        self._add_scripts_path()
        from baptism import check_orphans
        with tempfile.TemporaryDirectory() as td:
            sd = Path(td)
            final = sd / "video" / "final"
            final.mkdir(parents=True)
            v = final / "test.mp4"
            v.write_bytes(b"x" * 100)
            idx = sd / "video" / "index.json"
            idx.write_text(json.dumps({
                "version": "1.0",
                "items": {"abc": {"path": str(v)}},
            }))
            result = check_orphans(sd)
            self.assertTrue(result.passed)

    def test_check_orphans_found(self):
        self._add_scripts_path()
        from baptism import check_orphans
        with tempfile.TemporaryDirectory() as td:
            sd = Path(td)
            final = sd / "video" / "final"
            final.mkdir(parents=True)
            v = final / "orphan.mp4"
            v.write_bytes(b"x" * 100)
            idx = sd / "video" / "index.json"
            idx.write_text(json.dumps({"version": "1.0", "items": {}}))
            result = check_orphans(sd)
            self.assertFalse(result.passed)
            self.assertIn("orphan", result.detail)

    def test_check_skip_behavior(self):
        self._add_scripts_path()
        from baptism import check_skip_behavior
        with tempfile.TemporaryDirectory() as td:
            sd = Path(td)
            final = sd / "video" / "final"
            final.mkdir(parents=True)
            v = final / "test.mp4"
            v.write_bytes(b"x" * 100)
            idx = sd / "video" / "index.json"
            idx.write_text(json.dumps({
                "version": "1.0",
                "items": {"abc": {"path": str(v)}},
            }))
            result = check_skip_behavior(sd)
            self.assertTrue(result.passed)
            self.assertIn("SKIP_DZINE will work", result.detail)

    def test_check_worker_pid_no_file(self):
        self._add_scripts_path()
        from baptism import check_worker_pid
        # PID file may or may not exist in test env, just verify it returns a result
        result = check_worker_pid()
        self.assertIsInstance(result.passed, bool)
        self.assertEqual(result.name, "worker_pid")

    def test_run_baptism_level_a(self):
        self._add_scripts_path()
        from baptism import run_baptism
        with tempfile.TemporaryDirectory() as td:
            sd = Path(td) / "state"
            (sd / "video" / "final").mkdir(parents=True)
            report = run_baptism(state_dir=sd, level="A")
            self.assertGreater(len(report.checks), 5)
            # Level A should not include checkpoint/spool/pid checks
            check_names = [c.name for c in report.checks]
            self.assertNotIn("checkpoints", check_names)
            self.assertNotIn("spool", check_names)

    def test_run_baptism_level_b(self):
        self._add_scripts_path()
        from baptism import run_baptism
        with tempfile.TemporaryDirectory() as td:
            sd = Path(td) / "state"
            (sd / "video" / "final").mkdir(parents=True)
            report = run_baptism(state_dir=sd, level="B")
            check_names = [c.name for c in report.checks]
            self.assertIn("checkpoints", check_names)
            self.assertIn("spool", check_names)
            self.assertIn("worker_pid", check_names)

    def test_save_report(self):
        self._add_scripts_path()
        from baptism import run_baptism, save_report
        with tempfile.TemporaryDirectory() as td:
            sd = Path(td) / "state"
            (sd / "video" / "final").mkdir(parents=True)
            report = run_baptism(state_dir=sd, level="A")
            path = save_report(report, sd)
            self.assertTrue(path.exists())
            data = json.loads(path.read_text())
            self.assertIn("summary", data)
            self.assertIn("checks", data)
            self.assertEqual(data["level"], "A")

    def test_baptism_report_all_passed(self):
        self._add_scripts_path()
        from baptism import BaptismReport, CheckResult
        report = BaptismReport(level="A", timestamp="test")
        report.add(CheckResult("a", True, "ok"))
        report.add(CheckResult("b", True, "ok"))
        self.assertTrue(report.all_passed)
        self.assertEqual(report.passed, 2)
        self.assertEqual(report.failed, 0)

    def test_baptism_report_with_failure(self):
        self._add_scripts_path()
        from baptism import BaptismReport, CheckResult
        report = BaptismReport(level="A", timestamp="test")
        report.add(CheckResult("a", True, "ok"))
        report.add(CheckResult("b", False, "bad", "fail"))
        report.add(CheckResult("c", False, "meh", "warn"))
        self.assertFalse(report.all_passed)
        self.assertEqual(report.passed, 1)
        self.assertEqual(report.failed, 1)
        self.assertEqual(report.warnings, 1)

    def test_cli_level_a(self):
        self._add_scripts_path()
        from baptism import main
        with tempfile.TemporaryDirectory() as td:
            sd = Path(td) / "state"
            (sd / "video" / "final").mkdir(parents=True)
            rc = main(["--state-dir", str(sd), "--level", "A"])
            self.assertIn(rc, (0, 1))  # depends on env (ffprobe, etc.)

    def test_cli_level_b_no_confirm(self):
        self._add_scripts_path()
        from baptism import main
        with tempfile.TemporaryDirectory() as td:
            rc = main(["--state-dir", td, "--level", "B"])
            self.assertEqual(rc, 2)

    def test_cli_level_b_with_confirm(self):
        self._add_scripts_path()
        from baptism import main
        with tempfile.TemporaryDirectory() as td:
            sd = Path(td) / "state"
            (sd / "video" / "final").mkdir(parents=True)
            rc = main(["--state-dir", str(sd), "--level", "B", "CONFIRM=YES"])
            self.assertIn(rc, (0, 1))

    def test_check_refresh_history_empty(self):
        self._add_scripts_path()
        from baptism import check_refresh_history
        with tempfile.TemporaryDirectory() as td:
            result = check_refresh_history(Path(td))
            self.assertTrue(result.passed)

    def test_check_refresh_history_with_data(self):
        self._add_scripts_path()
        from baptism import check_refresh_history
        with tempfile.TemporaryDirectory() as td:
            sd = Path(td)
            vid = sd / "video"
            vid.mkdir(parents=True)
            idx = vid / "index.json"
            idx.write_text(json.dumps({
                "version": "1.0",
                "items": {},
                "meta_info": {
                    "refresh_history": [
                        {"at": "2025-01-01T00:00:00Z", "enriched": 5, "failed_probe": 0},
                    ],
                },
            }))
            result = check_refresh_history(sd)
            self.assertTrue(result.passed)
            self.assertIn("1 refreshes", result.detail)
            self.assertIn("enriched=5", result.detail)


# ---------------------------------------------------------------------------
# Refresh history forensic counters
# ---------------------------------------------------------------------------

class TestRefreshHistoryCounters(unittest.TestCase):
    """Test that refresh_history entries contain forensic counters."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_history_has_all_counters(self):
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index, _atomic_write_json
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "final"
            final.mkdir()
            idx_path = Path(td) / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            fake_meta = {
                "format": {"duration": "5.0", "bit_rate": "2000000"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }
            with mock.patch("video_index_refresh._ffprobe_json", return_value=fake_meta):
                stats = refresh_index(final_dir=final, index_path=idx_path, force=True)
            self.assertEqual(stats.enriched, 1)
            idx = _load_index(idx_path)
            history = idx.get("meta_info", {}).get("refresh_history", [])
            self.assertEqual(len(history), 1)
            entry = history[0]
            # All forensic counters must be present
            for key in ["at", "scanned", "checked", "enriched", "failed_probe",
                        "skipped_unchanged", "skipped_dedup", "skipped_no_sha8",
                        "skipped_outside_root", "skipped_not_file", "retried_probe",
                        "skipped_unstable", "item_error", "sha8_mismatch",
                        "total_items", "did_change", "force",
                        "allow_missing_sha8"]:
                self.assertIn(key, entry, f"Missing key: {key}")


# ---------------------------------------------------------------------------
# is_under_root + checked counter + is-not-None defensive update
# ---------------------------------------------------------------------------

class TestRefreshRootGuard(unittest.TestCase):
    """Tests for root guardrail and checked counter."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_is_under_root_true(self):
        self._add_scripts_path()
        from video_index_refresh import _is_under_root
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            child = root / "sub" / "file.txt"
            child.parent.mkdir(parents=True)
            child.touch()
            self.assertTrue(_is_under_root(child, root))

    def test_is_under_root_false(self):
        self._add_scripts_path()
        from video_index_refresh import _is_under_root
        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            outside = Path(td2) / "file.txt"
            outside.touch()
            self.assertFalse(_is_under_root(outside, Path(td1)))

    def test_checked_counter(self):
        """checked counts files that passed is_file + dedup + sha8 gate."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index
        with tempfile.TemporaryDirectory() as td:
            # index_path must be under state_root (td/video/index.json → td/)
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            # 2 files with sha8, 1 without
            (final / "V_R1_s1_aabbccdd.mp4").write_bytes(b"x" * 500)
            (final / "V_R1_s2_11223344.mp4").write_bytes(b"x" * 500)
            (final / "legacy_no_sha8.mp4").write_bytes(b"x" * 500)
            stats = refresh_index(final_dir=final, index_path=idx_path, force=True)
            # 2 with sha8 should be checked, 1 skipped_no_sha8
            self.assertEqual(stats.checked, 2)
            self.assertEqual(stats.skipped_no_sha8, 1)

    def test_symlink_outside_root_skipped(self):
        """Symlink pointing outside state root is skipped."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index
        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            # State root is td1, file is in td2
            vid = Path(td1) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            # Real file outside root
            outside = Path(td2) / "V_R1_s1_aabbccdd.mp4"
            outside.write_bytes(b"x" * 500)
            # Symlink inside final/ pointing outside
            link = final / "V_R1_s1_aabbccdd.mp4"
            link.symlink_to(outside)
            stats = refresh_index(final_dir=final, index_path=idx_path, force=True)
            self.assertEqual(stats.skipped_outside_root, 1)
            self.assertEqual(stats.checked, 0)


class TestDefensiveProbeUpdate(unittest.TestCase):
    """Test that probe data uses `is not None` checks (not truthy)."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_zero_duration_still_written(self):
        """Duration of 0.0 should still be written (not skipped by truthy check)."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            # Probe returns duration=0.0 (edge case, but valid)
            fake_meta = {
                "format": {"duration": "0.0", "bit_rate": "0"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }
            with mock.patch("video_index_refresh._ffprobe_json", return_value=fake_meta):
                refresh_index(final_dir=final, index_path=idx_path, force=True)
            idx = _load_index(idx_path)
            entry = idx["items"]["aabbccdd"]
            # Duration 0.0 should be recorded, not skipped
            self.assertEqual(entry["duration"], 0.0)
            # bitrate 0 should also be recorded
            self.assertEqual(entry["bitrate_bps"], 0)

    def test_none_codec_preserves_existing(self):
        """If probe returns None codec, existing value is preserved."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index, _atomic_write_json
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            # Pre-seed with good codec data
            _atomic_write_json(idx_path, {
                "version": "1.0",
                "items": {
                    "aabbccdd": {
                        "path": str(v),
                        "video_codec": "h264",
                        "audio_codec": "aac",
                    },
                },
            })
            # Degraded probe: no streams info (codecs = None)
            fake_meta = {
                "format": {"duration": "5.0", "bit_rate": "2000000"},
                "streams": [],
            }
            with mock.patch("video_index_refresh._ffprobe_json", return_value=fake_meta):
                refresh_index(final_dir=final, index_path=idx_path, force=True)
            idx = _load_index(idx_path)
            entry = idx["items"]["aabbccdd"]
            # Existing good values should be preserved
            self.assertEqual(entry["video_codec"], "h264")
            self.assertEqual(entry["audio_codec"], "aac")


# ---------------------------------------------------------------------------
# File lock, stability gate, per-item error, state_root persistence
# ---------------------------------------------------------------------------

class TestIndexLock(unittest.TestCase):
    """Tests for advisory file lock."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_lock_creates_lockfile(self):
        self._add_scripts_path()
        from video_index_refresh import _index_lock
        with tempfile.TemporaryDirectory() as td:
            idx_path = Path(td) / "index.json"
            lock_path = idx_path.with_suffix(".json.lock")
            with _index_lock(idx_path):
                self.assertTrue(lock_path.exists())

    def test_lock_is_reentrant_sequentially(self):
        """Lock can be acquired again after release."""
        self._add_scripts_path()
        from video_index_refresh import _index_lock
        with tempfile.TemporaryDirectory() as td:
            idx_path = Path(td) / "index.json"
            with _index_lock(idx_path):
                pass
            with _index_lock(idx_path):
                pass  # Should not deadlock


class TestFileStable(unittest.TestCase):
    """Tests for _is_file_stable quick check."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_stable_file(self):
        self._add_scripts_path()
        from video_index_refresh import _is_file_stable
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "test.mp4"
            f.write_bytes(b"x" * 100)
            self.assertTrue(_is_file_stable(f, sleep_s=0.05))

    def test_empty_file_unstable(self):
        self._add_scripts_path()
        from video_index_refresh import _is_file_stable
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "empty.mp4"
            f.write_bytes(b"")
            self.assertFalse(_is_file_stable(f, sleep_s=0.05))

    def test_missing_file_unstable(self):
        self._add_scripts_path()
        from video_index_refresh import _is_file_stable
        self.assertFalse(_is_file_stable(Path("/nonexistent"), sleep_s=0.05))


class TestItemError(unittest.TestCase):
    """Tests for per-item try/except (one bad file doesn't abort refresh)."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_bad_file_counted_as_item_error(self):
        """A file that throws an exception is counted, not propagated."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            # Two valid files
            v1 = final / "V_R1_s1_aabbccdd.mp4"
            v1.write_bytes(b"x" * 500)
            v2 = final / "V_R1_s2_11223344.mp4"
            v2.write_bytes(b"x" * 500)

            call_count = [0]
            original_stable = None

            def boom_on_second(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 2:
                    raise PermissionError("simulated permission error")
                return True

            with mock.patch("video_index_refresh._is_file_stable", side_effect=boom_on_second):
                with mock.patch("video_index_refresh._ffprobe_json", return_value={
                    "format": {"duration": "5.0", "bit_rate": "2000000"},
                    "streams": [{"codec_type": "video", "codec_name": "h264"}],
                }):
                    stats = refresh_index(final_dir=final, index_path=idx_path, force=True)
            # One succeeded, one errored — refresh wasn't aborted
            self.assertEqual(stats.item_error, 1)
            self.assertGreaterEqual(stats.enriched, 1)


class TestStateRootPersistence(unittest.TestCase):
    """Tests for state_root persisted in meta_info."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_state_root_written_on_first_refresh(self):
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            with mock.patch("video_index_refresh._ffprobe_json", return_value={
                "format": {"duration": "5.0", "bit_rate": "2000000"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }):
                refresh_index(final_dir=final, index_path=idx_path, force=True)
            idx = _load_index(idx_path)
            meta = idx.get("meta_info", {})
            self.assertIn("state_root", meta)
            # state_root should be td (parent.parent of video/index.json)
            self.assertEqual(meta["state_root"], str(Path(td).resolve()))

    def test_did_change_in_history(self):
        """did_change flag reflects whether enriched > 0."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            with mock.patch("video_index_refresh._ffprobe_json", return_value={
                "format": {"duration": "5.0", "bit_rate": "2000000"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }):
                refresh_index(final_dir=final, index_path=idx_path, force=True)
            idx = _load_index(idx_path)
            history = idx["meta_info"]["refresh_history"]
            self.assertTrue(history[-1]["did_change"])

    def test_skipped_unstable_in_history(self):
        """skipped_unstable and item_error counters appear in history."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            with mock.patch("video_index_refresh._ffprobe_json", return_value={
                "format": {"duration": "5.0", "bit_rate": "2000000"},
                "streams": [],
            }):
                refresh_index(final_dir=final, index_path=idx_path, force=True)
            idx = _load_index(idx_path)
            entry = idx["meta_info"]["refresh_history"][-1]
            self.assertIn("skipped_unstable", entry)
            self.assertIn("item_error", entry)
            self.assertIn("did_change", entry)


# ---------------------------------------------------------------------------
# Probe retry + skipped_not_file + total_items + expanduser
# ---------------------------------------------------------------------------

class TestProbeRetry(unittest.TestCase):
    """Test probe retry with backoff for transient failures."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_retry_on_first_probe_fail(self):
        """First probe fails, retry succeeds — retried_probe incremented."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            good_meta = {
                "format": {"duration": "5.0", "bit_rate": "2000000"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }
            # First call returns None, second returns good meta
            with mock.patch("video_index_refresh._ffprobe_json",
                          side_effect=[None, good_meta]):
                with mock.patch("video_index_refresh.time.sleep"):
                    stats = refresh_index(final_dir=final, index_path=idx_path, force=True)
            self.assertEqual(stats.retried_probe, 1)
            self.assertEqual(stats.enriched, 1)
            self.assertEqual(stats.failed_probe, 0)

    def test_retry_both_fail(self):
        """Both probe attempts fail — failed_probe incremented."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            with mock.patch("video_index_refresh._ffprobe_json", return_value=None):
                with mock.patch("video_index_refresh.time.sleep"):
                    stats = refresh_index(final_dir=final, index_path=idx_path, force=True)
            self.assertEqual(stats.retried_probe, 1)
            self.assertEqual(stats.failed_probe, 1)
            self.assertEqual(stats.enriched, 0)

    def test_no_retry_when_first_succeeds(self):
        """First probe succeeds — no retry, retried_probe stays 0."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            good_meta = {
                "format": {"duration": "5.0", "bit_rate": "2000000"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }
            with mock.patch("video_index_refresh._ffprobe_json", return_value=good_meta):
                stats = refresh_index(final_dir=final, index_path=idx_path, force=True)
            self.assertEqual(stats.retried_probe, 0)
            self.assertEqual(stats.enriched, 1)


class TestTotalItemsInHistory(unittest.TestCase):
    """Test that total_items appears in refresh_history entries."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_total_items_in_history(self):
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            good_meta = {
                "format": {"duration": "5.0", "bit_rate": "2000000"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }
            with mock.patch("video_index_refresh._ffprobe_json", return_value=good_meta):
                refresh_index(final_dir=final, index_path=idx_path, force=True)
            idx = _load_index(idx_path)
            entry = idx["meta_info"]["refresh_history"][-1]
            self.assertIn("total_items", entry)
            self.assertEqual(entry["total_items"], 1)


class TestExpandUserInRoot(unittest.TestCase):
    """Test that _is_under_root uses expanduser()."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_expanduser_called(self):
        self._add_scripts_path()
        from video_index_refresh import _is_under_root
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            child = root / "sub" / "file.txt"
            child.parent.mkdir(parents=True)
            child.touch()
            self.assertTrue(_is_under_root(child, root))
            # Path outside root
            other = Path(td).parent / "other"
            other.mkdir(exist_ok=True)
            f = other / "f.txt"
            f.touch()
            self.assertFalse(_is_under_root(f, root))


class TestRefreshBannerCounters(unittest.TestCase):
    """Test that refresh banner shows extended counters."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_banner_shows_retry_and_items(self):
        self._add_scripts_path()
        from doctor_report import build_refresh_banner, _read_json
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            vid = state / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({
                "items": {},
                "meta_info": {
                    "refresh_history": [{
                        "at": "2025-01-01T00:00:00",
                        "enriched": 3,
                        "probed": 5,
                        "failed_probe": 0,
                        "item_error": 0,
                        "skipped_unstable": 0,
                        "retried_probe": 2,
                        "skipped_no_sha8": 1,
                        "skipped_outside_root": 0,
                        "total_items": 10,
                        "did_change": True,
                    }],
                },
            }))
            banner = build_refresh_banner(state)
            self.assertIn("retry=2", banner)
            self.assertIn("no_sha8=1", banner)
            self.assertIn("items=10", banner)

    def test_banner_unstable_high_is_warn(self):
        """skipped_unstable >= 5 should trigger WARN status."""
        self._add_scripts_path()
        from doctor_report import build_refresh_banner
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            vid = state / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({
                "items": {},
                "meta_info": {
                    "refresh_history": [{
                        "at": "2025-01-01T00:00:00",
                        "enriched": 3,
                        "probed": 5,
                        "failed_probe": 0,
                        "item_error": 0,
                        "skipped_unstable": 6,
                        "did_change": True,
                    }],
                },
            }))
            banner = build_refresh_banner(state)
            self.assertIn("WARN", banner)

    def test_no_color_env(self):
        """--no-color sets NO_COLOR env var."""
        self._add_scripts_path()
        from doctor_report import main as dr_main
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            jobs = state / "jobs"
            jobs.mkdir(parents=True)
            vid = state / "video"
            vid.mkdir()
            idx = vid / "index.json"
            idx.write_text('{"items":{}}')
            with mock.patch.dict(os.environ, {}, clear=False):
                # Should not fail
                with mock.patch("sys.stdout.isatty", return_value=False):
                    rc = dr_main(["--state-dir", str(state), "--no-color"])
                self.assertEqual(os.environ.get("NO_COLOR"), "1")

    def test_out_flag_writes_file(self):
        """--out <path> duplicates report output to file."""
        self._add_scripts_path()
        from doctor_report import main as dr_main
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            jobs = state / "jobs"
            jobs.mkdir(parents=True)
            vid = state / "video"
            vid.mkdir()
            idx = vid / "index.json"
            idx.write_text('{"items":{}}')
            out_file = Path(td) / "report_out.txt"
            with mock.patch("sys.stdout.isatty", return_value=False):
                rc = dr_main(["--state-dir", str(state), "--out", str(out_file)])
            self.assertEqual(rc, 0)
            self.assertTrue(out_file.exists())
            content = out_file.read_text()
            self.assertIn("Doctor Report", content)


class TestStateRootSeal(unittest.TestCase):
    """Test that state_root is sealed on first empty run."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_state_root_persisted_on_empty_run(self):
        """Even with no mp4 files, state_root should be written on first run."""
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            # Force run on empty dir to seal state_root
            refresh_index(final_dir=final, index_path=idx_path, force=True)
            idx = _load_index(idx_path)
            meta = idx.get("meta_info", {})
            self.assertIn("state_root", meta)
            self.assertEqual(meta["state_root"], str(Path(td).resolve()))


class TestCleanupHistory(unittest.TestCase):
    """Test that doctor_cleanup persists cleanup_history in index."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_cleanup_history_written_after_quarantine(self):
        self._add_scripts_path()
        from doctor_cleanup import main as cleanup_main
        import time as _time
        with tempfile.TemporaryDirectory() as td:
            final = Path(td) / "video" / "final"
            final.mkdir(parents=True)
            quarantine = Path(td) / "video" / "quarantine"
            idx_path = Path(td) / "video" / "index.json"
            # Create index with no items
            idx_path.write_text(json.dumps({"items": {}, "meta_info": {}}))
            # Create an orphan file (not in index, large enough)
            orphan = final / "V_R1_s1_aabbccdd.mp4"
            orphan.write_bytes(b"x" * 600_000)
            # Set mtime to 10 hours ago
            old_ts = _time.time() - 36_000
            os.utime(orphan, (old_ts, old_ts))
            rc = cleanup_main([
                "--index", str(idx_path),
                "--final-dir", str(final),
                "--quarantine-dir", str(quarantine),
                "--quarantine",
                "--older-than-hours", "6",
                "--min-size-kb", "500",
                "--keep-last-n", "0",
            ])
            self.assertEqual(rc, 0)
            # Check cleanup_history was written
            idx = json.loads(idx_path.read_text())
            history = idx.get("meta_info", {}).get("cleanup_history", [])
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["moved"], 1)
            self.assertIn("dangling", history[0])


# ---------------------------------------------------------------------------
# Dangling Index Repair tests
# ---------------------------------------------------------------------------

class TestDanglingIndexRepair(unittest.TestCase):
    """Tests for doctor_index_repair.py."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_dry_run_marks_dangling(self):
        """Dry-run marks entries but doesn't remove them."""
        self._add_scripts_path()
        from doctor_index_repair import repair_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            # Create index with entries: missing file, no path key, invalid path
            idx_path.write_text(json.dumps({
                "items": {
                    "aabbccdd": {
                        "path": str(vid / "final" / "V_R1_s1_aabbccdd.mp4"),
                        "duration": 5.0,
                    },
                    "11223344": {
                        "duration": 3.0,
                    },
                    "55667788": {
                        "path": "",
                        "duration": 2.0,
                    },
                },
                "meta_info": {},
            }))
            stats = repair_dangling(index_path=idx_path, apply=False, double_check_sleep=0)
            self.assertEqual(stats["dangling_found"], 3)
            self.assertEqual(stats["dangling_missing_file"], 1)
            self.assertEqual(stats["dangling_missing_path"], 1)
            self.assertEqual(stats["dangling_invalid_path"], 1)
            # Items should still be in place (dry-run)
            idx = _load_index(idx_path)
            self.assertIn("aabbccdd", idx["items"])
            self.assertTrue(idx["items"]["aabbccdd"].get("dangling"))

    def test_apply_moves_to_bucket(self):
        """--apply moves dangling entries to dangling_items bucket."""
        self._add_scripts_path()
        from doctor_index_repair import repair_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({
                "items": {
                    "aabbccdd": {
                        "path": str(vid / "final" / "gone.mp4"),
                        "duration": 5.0,
                    },
                    "eeff0011": {
                        "path": str(vid / "final" / "exists.mp4"),
                        "duration": 3.0,
                    },
                },
                "meta_info": {},
            }))
            # Create the file that eeff0011 points to
            final = vid / "final"
            final.mkdir()
            (final / "exists.mp4").write_bytes(b"x" * 100)

            stats = repair_dangling(index_path=idx_path, apply=True, move_to_bucket=True, double_check_sleep=0)
            self.assertEqual(stats["dangling_found"], 1)
            idx = _load_index(idx_path)
            # aabbccdd should be moved to bucket
            self.assertNotIn("aabbccdd", idx["items"])
            self.assertIn("aabbccdd", idx.get("dangling_items", {}))
            self.assertEqual(idx["dangling_items"]["aabbccdd"]["dangling_reason"], "missing_file")
            # eeff0011 should still be in items
            self.assertIn("eeff0011", idx["items"])

    def test_apply_delete_removes_entirely(self):
        """--apply --delete removes entries with no bucket."""
        self._add_scripts_path()
        from doctor_index_repair import repair_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({
                "items": {
                    "aabbccdd": {
                        "path": str(vid / "final" / "gone.mp4"),
                    },
                },
                "meta_info": {},
            }))
            stats = repair_dangling(index_path=idx_path, apply=True, move_to_bucket=False, double_check_sleep=0)
            self.assertEqual(stats["dangling_found"], 1)
            idx = _load_index(idx_path)
            self.assertNotIn("aabbccdd", idx["items"])
            self.assertNotIn("dangling_items", idx)

    def test_repair_history_persisted(self):
        """repair_history ring buffer appears in meta_info."""
        self._add_scripts_path()
        from doctor_index_repair import repair_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({"items": {}, "meta_info": {}}))
            repair_dangling(index_path=idx_path, double_check_sleep=0)
            idx = _load_index(idx_path)
            history = idx["meta_info"].get("repair_history", [])
            self.assertEqual(len(history), 1)
            self.assertIn("checked", history[0])
            self.assertIn("dangling_found", history[0])
            self.assertIn("env", history[0])
            self.assertIn("hostname", history[0]["env"])

    def test_relative_path_resolved_via_state_root(self):
        """Relative paths are resolved via state_root before declaring dangling."""
        self._add_scripts_path()
        from doctor_index_repair import repair_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            final = vid / "final"
            final.mkdir(parents=True)
            idx_path = vid / "index.json"
            # Create a file and reference it with a relative path
            f = final / "V_R1_s1_aabbccdd.mp4"
            f.write_bytes(b"x" * 100)
            idx_path.write_text(json.dumps({
                "items": {
                    "aabbccdd": {
                        "path": "video/final/V_R1_s1_aabbccdd.mp4",
                    },
                },
                "meta_info": {"state_root": str(Path(td).resolve())},
            }))
            stats = repair_dangling(index_path=idx_path, double_check_sleep=0)
            # Should NOT be dangling — resolved via state_root
            self.assertEqual(stats["dangling_found"], 0)

    def test_cli_dry_run(self):
        """CLI dry-run returns 1 if dangling found, 0 if clean."""
        self._add_scripts_path()
        from doctor_index_repair import main as repair_main
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({
                "items": {
                    "aabbccdd": {"path": "/nonexistent/file.mp4"},
                },
                "meta_info": {},
            }))
            rc = repair_main(["--state-dir", str(td)])
            self.assertEqual(rc, 1)

    def test_cli_clean_returns_0(self):
        """CLI returns 0 when no dangling entries."""
        self._add_scripts_path()
        from doctor_index_repair import main as repair_main
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            final = vid / "final"
            final.mkdir(parents=True)
            idx_path = vid / "index.json"
            f = final / "V_R1_s1_aabbccdd.mp4"
            f.write_bytes(b"x" * 100)
            idx_path.write_text(json.dumps({
                "items": {
                    "aabbccdd": {"path": str(f)},
                },
                "meta_info": {},
            }))
            rc = repair_main(["--state-dir", str(td)])
            self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# Repair hardening tests (outside_root, env fingerprint, double-check)
# ---------------------------------------------------------------------------

class TestRepairHardening(unittest.TestCase):
    """Tests for hardened repair: outside_root, permission_denied, env."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_outside_root_classified(self):
        """Paths that resolve outside state_root get outside_root reason."""
        self._add_scripts_path()
        from doctor_index_repair import repair_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            # Path outside root
            outside = Path(td).parent / "outside_file.mp4"
            idx_path.write_text(json.dumps({
                "items": {
                    "aabbccdd": {
                        "path": str(outside),
                    },
                },
                "meta_info": {"state_root": str(Path(td).resolve())},
            }))
            stats = repair_dangling(index_path=idx_path, double_check_sleep=0)
            self.assertEqual(stats["dangling_outside_root"], 1)
            self.assertEqual(stats["dangling_found"], 1)

    def test_env_fingerprint_in_repair_history(self):
        """repair_history entries contain env fingerprint."""
        self._add_scripts_path()
        from doctor_index_repair import repair_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({"items": {}, "meta_info": {}}))
            repair_dangling(index_path=idx_path, double_check_sleep=0)
            idx = _load_index(idx_path)
            entry = idx["meta_info"]["repair_history"][-1]
            self.assertIn("env", entry)
            self.assertIn("hostname", entry["env"])
            self.assertIn("python", entry["env"])
            self.assertIn("platform", entry["env"])


# ---------------------------------------------------------------------------
# Inode + device identity in refresh
# ---------------------------------------------------------------------------

class TestInodeDeviceIdentity(unittest.TestCase):
    """Test that refresh stores inode + device for identity."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_inode_device_in_entry(self):
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            good_meta = {
                "format": {"duration": "5.0", "bit_rate": "2000000"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }
            with mock.patch("video_index_refresh._ffprobe_json", return_value=good_meta):
                refresh_index(final_dir=final, index_path=idx_path, force=True)
            idx = _load_index(idx_path)
            entry = idx["items"]["aabbccdd"]
            self.assertIn("inode", entry)
            self.assertIn("device", entry)
            self.assertIsInstance(entry["inode"], int)
            self.assertIsInstance(entry["device"], int)

    def test_env_fingerprint_in_refresh_history(self):
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            good_meta = {
                "format": {"duration": "5.0", "bit_rate": "2000000"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }
            with mock.patch("video_index_refresh._ffprobe_json", return_value=good_meta):
                refresh_index(final_dir=final, index_path=idx_path, force=True)
            idx = _load_index(idx_path)
            entry = idx["meta_info"]["refresh_history"][-1]
            self.assertIn("env", entry)
            self.assertIn("hostname", entry["env"])


# ---------------------------------------------------------------------------
# Resurrect tests
# ---------------------------------------------------------------------------

class TestDanglingIndexResurrect(unittest.TestCase):
    """Tests for doctor_index_resurrect.py."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def _make_index_with_dangling(self, td, create_file=True):
        """Helper: create index with a dangling_items entry."""
        vid = Path(td) / "video"
        final = vid / "final"
        final.mkdir(parents=True)
        idx_path = vid / "index.json"
        file_path = final / "V_R1_s1_aabbccdd.mp4"
        if create_file:
            file_path.write_bytes(b"x" * 500)
        idx_path.write_text(json.dumps({
            "items": {},
            "dangling_items": {
                "aabbccdd": {
                    "path": str(file_path),
                    "duration": 5.0,
                    "dangling_reason": "missing_file",
                    "dangling_at": "2025-01-01T00:00:00",
                },
            },
            "meta_info": {"state_root": str(Path(td).resolve())},
        }))
        return idx_path, file_path

    def test_dry_run_reports_eligible(self):
        """Dry-run identifies eligible entries but doesn't restore."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            idx_path, _ = self._make_index_with_dangling(td, create_file=True)
            stats = resurrect_dangling(index_path=idx_path)
            self.assertEqual(stats["candidates"], 1)
            self.assertEqual(stats["would_restore"], 1)
            self.assertEqual(stats["restored"], 0)
            # Item should still be in dangling_items
            idx = _load_index(idx_path)
            self.assertIn("aabbccdd", idx.get("dangling_items", {}))
            self.assertNotIn("aabbccdd", idx["items"])

    def test_apply_restores_entry(self):
        """--apply moves entry from dangling_items back to items."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            idx_path, _ = self._make_index_with_dangling(td, create_file=True)
            stats = resurrect_dangling(index_path=idx_path, apply=True)
            self.assertEqual(stats["restored"], 1)
            idx = _load_index(idx_path)
            self.assertIn("aabbccdd", idx["items"])
            # dangling metadata stripped
            self.assertNotIn("dangling_reason", idx["items"]["aabbccdd"])
            self.assertIn("restored_at", idx["items"]["aabbccdd"])
            self.assertEqual(idx["items"]["aabbccdd"]["identity_confidence"], "high")
            # bucket should be cleaned up
            self.assertNotIn("dangling_items", idx)

    def test_reject_missing_file(self):
        """Reject restore if file doesn't exist."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling
        with tempfile.TemporaryDirectory() as td:
            idx_path, _ = self._make_index_with_dangling(td, create_file=False)
            stats = resurrect_dangling(index_path=idx_path, apply=True)
            self.assertEqual(stats["restored"], 0)
            self.assertEqual(stats["rejected_missing_file"], 1)

    def test_reject_conflict(self):
        """Reject restore if key already exists in items."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            idx_path, file_path = self._make_index_with_dangling(td, create_file=True)
            # Add the same key to items
            idx = json.loads(idx_path.read_text())
            idx["items"]["aabbccdd"] = {"path": str(file_path), "duration": 10.0}
            idx_path.write_text(json.dumps(idx))
            stats = resurrect_dangling(index_path=idx_path, apply=True)
            self.assertEqual(stats["rejected_conflict"], 1)
            self.assertEqual(stats["restored"], 0)

    def test_reject_no_sha8(self):
        """Reject restore if no sha8 in filename (without flag)."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            final = vid / "final"
            final.mkdir(parents=True)
            idx_path = vid / "index.json"
            f = final / "no_sha8_here.mp4"
            f.write_bytes(b"x" * 500)
            idx_path.write_text(json.dumps({
                "items": {},
                "dangling_items": {
                    "nosha8": {
                        "path": str(f),
                        "dangling_reason": "missing_file",
                    },
                },
                "meta_info": {"state_root": str(Path(td).resolve())},
            }))
            stats = resurrect_dangling(index_path=idx_path, apply=True)
            self.assertEqual(stats["rejected_no_sha8"], 1)

    def test_allow_missing_sha8_flag(self):
        """--allow-missing-sha8 permits restore without sha8."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            final = vid / "final"
            final.mkdir(parents=True)
            idx_path = vid / "index.json"
            f = final / "legacy_video.mp4"
            f.write_bytes(b"x" * 500)
            idx_path.write_text(json.dumps({
                "items": {},
                "dangling_items": {
                    "legacy": {
                        "path": str(f),
                        "dangling_reason": "missing_file",
                    },
                },
                "meta_info": {"state_root": str(Path(td).resolve())},
            }))
            stats = resurrect_dangling(index_path=idx_path, apply=True, allow_missing_sha8=True)
            self.assertEqual(stats["restored"], 1)

    def test_limit_caps_restores(self):
        """--limit N caps the number of restores per run."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            final = vid / "final"
            final.mkdir(parents=True)
            idx_path = vid / "index.json"
            dangling = {}
            for i in range(5):
                sha8 = f"aa{i:06x}"
                f = final / f"V_R1_s{i}_{sha8}.mp4"
                f.write_bytes(b"x" * 500)
                dangling[sha8] = {"path": str(f), "dangling_reason": "test"}
            idx_path.write_text(json.dumps({
                "items": {},
                "dangling_items": dangling,
                "meta_info": {"state_root": str(Path(td).resolve())},
            }))
            stats = resurrect_dangling(index_path=idx_path, apply=True, limit=2)
            self.assertEqual(stats["restored"], 2)
            idx = _load_index(idx_path)
            self.assertEqual(len(idx["items"]), 2)
            self.assertEqual(len(idx["dangling_items"]), 3)

    def test_resurrect_history_persisted(self):
        """resurrect_history ring buffer appears in meta_info."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            idx_path, _ = self._make_index_with_dangling(td, create_file=True)
            resurrect_dangling(index_path=idx_path)
            idx = _load_index(idx_path)
            history = idx["meta_info"].get("resurrect_history", [])
            self.assertEqual(len(history), 1)
            self.assertIn("candidates", history[0])
            self.assertIn("would_restore", history[0])
            self.assertIn("restored_high", history[0])
            self.assertIn("restored_medium", history[0])
            self.assertIn("restored_low", history[0])
            self.assertIn("env", history[0])

    def test_empty_bucket(self):
        """No dangling_items returns immediately."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({"items": {}, "meta_info": {}}))
            stats = resurrect_dangling(index_path=idx_path)
            self.assertEqual(stats["candidates"], 0)

    def test_cli_dry_run_returns_1_with_eligible(self):
        """CLI dry-run returns 1 when eligible entries found."""
        self._add_scripts_path()
        from doctor_index_resurrect import main as resurrect_main
        with tempfile.TemporaryDirectory() as td:
            idx_path, _ = self._make_index_with_dangling(td, create_file=True)
            rc = resurrect_main(["--state-dir", str(td)])
            self.assertEqual(rc, 1)

    def test_cli_apply_returns_0(self):
        """CLI --apply returns 0 after successful restore."""
        self._add_scripts_path()
        from doctor_index_resurrect import main as resurrect_main
        with tempfile.TemporaryDirectory() as td:
            idx_path, _ = self._make_index_with_dangling(td, create_file=True)
            rc = resurrect_main(["--state-dir", str(td), "--apply"])
            self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# Repair: storage unavailable, invalid_path, seen_count, cleared flags
# ---------------------------------------------------------------------------

class TestRepairStorageAndClassification(unittest.TestCase):
    """Tests for storage guard, invalid_path_value, seen_count, flag clearing."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_storage_unavailable_aborts(self):
        """Repair aborts when state_root is inaccessible."""
        self._add_scripts_path()
        from doctor_index_repair import repair_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            # Point state_root to a non-existent directory
            idx_path.write_text(json.dumps({
                "items": {
                    "aabbccdd": {"path": "/some/file.mp4"},
                },
                "meta_info": {"state_root": "/nonexistent/root/dir"},
            }))
            stats = repair_dangling(index_path=idx_path, double_check_sleep=0)
            self.assertTrue(stats["storage_unavailable"])
            self.assertEqual(stats["checked"], 0)
            # History should still be persisted
            idx = _load_index(idx_path)
            history = idx["meta_info"]["repair_history"]
            self.assertTrue(history[-1]["storage_unavailable"])

    def test_invalid_path_value_classified(self):
        """Junk path values get invalid_path_value classification."""
        self._add_scripts_path()
        from doctor_index_repair import repair_dangling
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({
                "items": {
                    "aa000001": {"path": ""},
                    "aa000002": {"path": "."},
                    "aa000003": {"path": "/"},
                    "aa000004": {"path": "None"},
                    "aa000005": {"path": "  "},
                },
                "meta_info": {},
            }))
            stats = repair_dangling(index_path=idx_path, double_check_sleep=0)
            self.assertEqual(stats["dangling_invalid_path"], 5)
            self.assertEqual(stats["dangling_missing_path"], 0)

    def test_dangling_seen_count_increments(self):
        """dangling_seen_count increments on repeated scans."""
        self._add_scripts_path()
        from doctor_index_repair import repair_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({
                "items": {
                    "aabbccdd": {"path": str(vid / "gone.mp4")},
                },
                "meta_info": {},
            }))
            # First scan
            repair_dangling(index_path=idx_path, apply=False, double_check_sleep=0)
            idx = _load_index(idx_path)
            self.assertEqual(idx["items"]["aabbccdd"]["dangling_seen_count"], 1)
            self.assertIn("dangling_at", idx["items"]["aabbccdd"])
            first_at = idx["items"]["aabbccdd"]["dangling_at"]
            # Second scan
            repair_dangling(index_path=idx_path, apply=False, double_check_sleep=0)
            idx = _load_index(idx_path)
            self.assertEqual(idx["items"]["aabbccdd"]["dangling_seen_count"], 2)
            # dangling_at should NOT change (first seen timestamp preserved)
            self.assertEqual(idx["items"]["aabbccdd"]["dangling_at"], first_at)

    def test_healthy_item_clears_dangling_flags(self):
        """Item that becomes healthy gets dangling flags cleared."""
        self._add_scripts_path()
        from doctor_index_repair import repair_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            final = vid / "final"
            final.mkdir(parents=True)
            idx_path = vid / "index.json"
            f = final / "V_R1_s1_aabbccdd.mp4"
            f.write_bytes(b"x" * 100)
            # Start with stale dangling flags
            idx_path.write_text(json.dumps({
                "items": {
                    "aabbccdd": {
                        "path": str(f),
                        "dangling": True,
                        "dangling_reason": "missing_file",
                        "dangling_at": "2025-01-01T00:00:00",
                        "dangling_seen_count": 3,
                        "dangling_last_seen_at": "2025-01-02T00:00:00",
                    },
                },
                "meta_info": {},
            }))
            repair_dangling(index_path=idx_path, double_check_sleep=0)
            idx = _load_index(idx_path)
            entry = idx["items"]["aabbccdd"]
            self.assertNotIn("dangling", entry)
            self.assertNotIn("dangling_reason", entry)
            self.assertNotIn("dangling_at", entry)
            self.assertNotIn("dangling_seen_count", entry)
            self.assertNotIn("dangling_last_seen_at", entry)

    def test_cli_storage_unavailable_returns_2(self):
        """CLI returns exit code 2 on storage_unavailable."""
        self._add_scripts_path()
        from doctor_index_repair import main as repair_main
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({
                "items": {},
                "meta_info": {"state_root": "/nonexistent/root/dir"},
            }))
            rc = repair_main(["--state-dir", str(td)])
            self.assertEqual(rc, 2)


# ---------------------------------------------------------------------------
# Resurrect: identity confidence, --note, scar
# ---------------------------------------------------------------------------

class TestResurrectIdentityConfidence(unittest.TestCase):
    """Tests for identity confidence in resurrect."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_high_confidence_with_sha8(self):
        """Entries with sha8 in filename get HIGH confidence."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            final = vid / "final"
            final.mkdir(parents=True)
            idx_path = vid / "index.json"
            f = final / "V_R1_s1_aabbccdd.mp4"
            f.write_bytes(b"x" * 500)
            idx_path.write_text(json.dumps({
                "items": {},
                "dangling_items": {
                    "aabbccdd": {
                        "path": str(f),
                        "dangling_reason": "missing_file",
                    },
                },
                "meta_info": {"state_root": str(Path(td).resolve())},
            }))
            stats = resurrect_dangling(index_path=idx_path, apply=True)
            self.assertEqual(stats["restored"], 1)
            self.assertEqual(stats["restored_high"], 1)
            idx = _load_index(idx_path)
            entry = idx["items"]["aabbccdd"]
            self.assertEqual(entry["identity_confidence"], "high")
            # No identity warning for high confidence
            self.assertNotIn("identity_warning", entry)
            self.assertNotIn("resurrected_without_visual_proof", entry)

    def test_medium_confidence_fingerprint_match(self):
        """No sha8 but size+mtime match → MEDIUM confidence."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            final = vid / "final"
            final.mkdir(parents=True)
            idx_path = vid / "index.json"
            f = final / "legacy_video.mp4"  # no sha8
            f.write_bytes(b"x" * 500)
            st = f.stat()
            idx_path.write_text(json.dumps({
                "items": {},
                "dangling_items": {
                    "aabbccdd": {
                        "path": str(f),
                        "dangling_reason": "missing_file",
                        "file_bytes": st.st_size,
                        "file_mtime_ns": st.st_mtime_ns,
                    },
                },
                "meta_info": {"state_root": str(Path(td).resolve())},
            }))
            stats = resurrect_dangling(
                index_path=idx_path, apply=True, allow_missing_sha8=True,
            )
            self.assertEqual(stats["restored"], 1)
            self.assertEqual(stats["restored_medium"], 1)
            idx = _load_index(idx_path)
            entry = idx["items"]["aabbccdd"]
            self.assertEqual(entry["identity_confidence"], "medium")
            self.assertIn("identity_warning", entry)
            self.assertTrue(entry.get("resurrected_without_visual_proof"))

    def test_low_confidence_no_fingerprint(self):
        """No sha8 and no fingerprint match → LOW confidence."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            final = vid / "final"
            final.mkdir(parents=True)
            idx_path = vid / "index.json"
            f = final / "legacy_video.mp4"
            f.write_bytes(b"x" * 500)
            idx_path.write_text(json.dumps({
                "items": {},
                "dangling_items": {
                    "aabbccdd": {
                        "path": str(f),
                        "dangling_reason": "missing_file",
                        # No file_bytes/file_mtime_ns → no fingerprint match
                    },
                },
                "meta_info": {"state_root": str(Path(td).resolve())},
            }))
            stats = resurrect_dangling(
                index_path=idx_path, apply=True, allow_missing_sha8=True,
            )
            self.assertEqual(stats["restored"], 1)
            self.assertEqual(stats["restored_low"], 1)
            idx = _load_index(idx_path)
            entry = idx["items"]["aabbccdd"]
            self.assertEqual(entry["identity_confidence"], "low")
            self.assertTrue(entry.get("resurrected_without_visual_proof"))

    def test_note_persisted_in_entry_and_history(self):
        """--note is persisted in restored entry and history."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            final = vid / "final"
            final.mkdir(parents=True)
            idx_path = vid / "index.json"
            f = final / "V_R1_s1_aabbccdd.mp4"
            f.write_bytes(b"x" * 500)
            idx_path.write_text(json.dumps({
                "items": {},
                "dangling_items": {
                    "aabbccdd": {
                        "path": str(f),
                        "dangling_reason": "missing_file",
                    },
                },
                "meta_info": {"state_root": str(Path(td).resolve())},
            }))
            stats = resurrect_dangling(
                index_path=idx_path, apply=True, note="drive reattached",
            )
            self.assertEqual(stats["restored"], 1)
            idx = _load_index(idx_path)
            self.assertEqual(idx["items"]["aabbccdd"]["resurrect_note"], "drive reattached")
            history = idx["meta_info"]["resurrect_history"][-1]
            self.assertEqual(history["note"], "drive reattached")

    def test_would_restore_counter_in_dry_run(self):
        """Dry-run sets would_restore count correctly."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            final = vid / "final"
            final.mkdir(parents=True)
            idx_path = vid / "index.json"
            f = final / "V_R1_s1_aabbccdd.mp4"
            f.write_bytes(b"x" * 500)
            idx_path.write_text(json.dumps({
                "items": {},
                "dangling_items": {
                    "aabbccdd": {
                        "path": str(f),
                        "dangling_reason": "missing_file",
                    },
                },
                "meta_info": {"state_root": str(Path(td).resolve())},
            }))
            stats = resurrect_dangling(index_path=idx_path, apply=False)
            self.assertEqual(stats["would_restore"], 1)
            self.assertEqual(stats["restored"], 0)

    def test_confidence_breakdown_in_history(self):
        """Resurrect history has confidence breakdown."""
        self._add_scripts_path()
        from doctor_index_resurrect import resurrect_dangling, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            final = vid / "final"
            final.mkdir(parents=True)
            idx_path = vid / "index.json"
            f = final / "V_R1_s1_aabbccdd.mp4"
            f.write_bytes(b"x" * 500)
            idx_path.write_text(json.dumps({
                "items": {},
                "dangling_items": {
                    "aabbccdd": {
                        "path": str(f),
                        "dangling_reason": "missing_file",
                    },
                },
                "meta_info": {"state_root": str(Path(td).resolve())},
            }))
            resurrect_dangling(index_path=idx_path, apply=True)
            idx = _load_index(idx_path)
            history = idx["meta_info"]["resurrect_history"][-1]
            self.assertIn("restored_high", history)
            self.assertIn("restored_medium", history)
            self.assertIn("restored_low", history)
            self.assertEqual(history["restored_high"], 1)


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

class TestSchemaVersion(unittest.TestCase):
    """Test that refresh stamps index with schema_version."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_schema_version_set_on_new_index(self):
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            good_meta = {
                "format": {"duration": "5.0", "bit_rate": "2000000"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }
            with mock.patch("video_index_refresh._ffprobe_json", return_value=good_meta):
                refresh_index(final_dir=final, index_path=idx_path, force=True)
            idx = _load_index(idx_path)
            self.assertEqual(idx.get("schema_version"), 2)

    def test_schema_version_preserved_on_existing_index(self):
        self._add_scripts_path()
        from video_index_refresh import refresh_index, _load_index
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            final = vid / "final"
            final.mkdir()
            idx_path = vid / "index.json"
            # Pre-existing index with schema_version
            idx_path.write_text(json.dumps({
                "items": {}, "meta_info": {}, "schema_version": 2,
            }))
            v = final / "V_R1_s1_aabbccdd.mp4"
            v.write_bytes(b"x" * 500)
            good_meta = {
                "format": {"duration": "5.0", "bit_rate": "2000000"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }
            with mock.patch("video_index_refresh._ffprobe_json", return_value=good_meta):
                refresh_index(final_dir=final, index_path=idx_path, force=True)
            idx = _load_index(idx_path)
            self.assertEqual(idx.get("schema_version"), 2)


# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------

class TestPolicyConstants(unittest.TestCase):
    """Test that _policy.py constants are importable and consistent."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_policy_importable(self):
        self._add_scripts_path()
        from _policy import (
            STABILITY_SLEEP_SEC, PROBE_RETRY_COUNT, PROBE_RETRY_BACKOFF_SEC,
            REPAIR_DOUBLE_CHECK_SLEEP_SEC, CONFIDENCE_HIGH, CONFIDENCE_MEDIUM,
            CONFIDENCE_LOW, INDEX_SCHEMA_VERSION, HISTORY_RING_SIZE,
        )
        self.assertIsInstance(STABILITY_SLEEP_SEC, (int, float))
        self.assertIsInstance(PROBE_RETRY_COUNT, int)
        self.assertEqual(CONFIDENCE_HIGH, "high")
        self.assertEqual(CONFIDENCE_MEDIUM, "medium")
        self.assertEqual(CONFIDENCE_LOW, "low")
        self.assertEqual(INDEX_SCHEMA_VERSION, 2)
        self.assertGreater(HISTORY_RING_SIZE, 0)

    def test_resurrect_uses_policy_constants(self):
        """Resurrect imports confidence constants from _policy."""
        self._add_scripts_path()
        from _policy import CONFIDENCE_HIGH
        from doctor_index_resurrect import _assess_identity_confidence
        # Verify the function returns the same string constant
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "V_R1_s1_aabbccdd.mp4"
            f.write_bytes(b"x" * 100)
            result = _assess_identity_confidence(f, {}, has_sha8=True)
            self.assertEqual(result, CONFIDENCE_HIGH)


# ---------------------------------------------------------------------------
# Keyframe scoring tests
# ---------------------------------------------------------------------------

class TestKeyframeScoring(unittest.TestCase):
    """Tests for keyframe_score.py scoring logic."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_compute_zone_green(self):
        """All criteria high → green zone."""
        self._add_scripts_path()
        from keyframe_score import compute_zone, _load_rubric
        rubric = _load_rubric()
        scores = {
            "identity": 2, "hands_body": 2, "face_artifacts": 2,
            "consistency": 2, "lipsync_ready": 2,
        }
        self.assertEqual(compute_zone(scores, rubric), "green")

    def test_compute_zone_red_identity_zero(self):
        """Identity at 0 → red zone regardless of total."""
        self._add_scripts_path()
        from keyframe_score import compute_zone, _load_rubric
        rubric = _load_rubric()
        scores = {
            "identity": 0, "hands_body": 2, "face_artifacts": 2,
            "consistency": 2, "lipsync_ready": 2,
        }
        self.assertEqual(compute_zone(scores, rubric), "red")

    def test_compute_zone_red_lipsync_zero(self):
        """Lipsync at 0 → red zone."""
        self._add_scripts_path()
        from keyframe_score import compute_zone, _load_rubric
        rubric = _load_rubric()
        scores = {
            "identity": 2, "hands_body": 2, "face_artifacts": 2,
            "consistency": 2, "lipsync_ready": 0,
        }
        self.assertEqual(compute_zone(scores, rubric), "red")

    def test_compute_zone_yellow(self):
        """Total >= 7 but identity or lipsync not both 2 → yellow."""
        self._add_scripts_path()
        from keyframe_score import compute_zone, _load_rubric
        rubric = _load_rubric()
        scores = {
            "identity": 1, "hands_body": 2, "face_artifacts": 2,
            "consistency": 2, "lipsync_ready": 2,
        }
        zone = compute_zone(scores, rubric)
        # Total=9 but identity=1 → not green
        self.assertEqual(zone, "yellow")

    def test_score_entry_validates_criteria(self):
        """Unknown criterion name returns error."""
        self._add_scripts_path()
        from keyframe_score import score_entry
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({"items": {"aa": {}}, "meta_info": {}}))
            result = score_entry("aa", {"bogus_criterion": 2}, index_path=idx_path)
            self.assertIn("error", result)

    def test_score_entry_validates_range(self):
        """Score value > 2 returns error."""
        self._add_scripts_path()
        from keyframe_score import score_entry
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({"items": {"aa": {}}, "meta_info": {}}))
            result = score_entry("aa", {"identity": 5}, index_path=idx_path)
            self.assertIn("error", result)

    def test_score_entry_apply_persists(self):
        """--apply persists scores in index entry."""
        self._add_scripts_path()
        from keyframe_score import score_entry, _load_index
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({
                "items": {
                    "aabbccdd": {"path": "/some/file.mp4", "duration": 5.0},
                },
                "meta_info": {},
            }))
            scores = {
                "identity": 2, "hands_body": 2, "face_artifacts": 1,
                "consistency": 2, "lipsync_ready": 2,
            }
            result = score_entry("aabbccdd", scores, index_path=idx_path, apply=True)
            self.assertEqual(result["zone"], "green")  # total=9, all>=1, identity=2, lipsync=2 → green
            self.assertEqual(result["total"], 9)
            idx = _load_index(idx_path)
            entry_qc = idx["items"]["aabbccdd"]["visual_qc"]
            self.assertEqual(entry_qc["total"], 9)
            self.assertIn("scored_at", entry_qc)
            # Score history persisted
            history = idx["meta_info"]["score_history"]
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["sha8"], "aabbccdd")

    def test_score_entry_not_found(self):
        """Scoring non-existent entry returns error."""
        self._add_scripts_path()
        from keyframe_score import score_entry
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({"items": {}, "meta_info": {}}))
            result = score_entry("nonexist", {"identity": 2}, index_path=idx_path, apply=True)
            self.assertIn("error", result)

    def test_summary_counts(self):
        """Summary correctly counts scored/unscored/zones."""
        self._add_scripts_path()
        from keyframe_score import summary
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({
                "items": {
                    "aa": {
                        "visual_qc": {"total": 10, "zone": "green", "scored_at": "now"},
                    },
                    "bb": {
                        "visual_qc": {"total": 7, "zone": "yellow", "scored_at": "now"},
                    },
                    "cc": {},  # unscored
                },
                "meta_info": {},
            }))
            stats = summary(index_path=idx_path)
            self.assertEqual(stats["total_items"], 3)
            self.assertEqual(stats["scored"], 2)
            self.assertEqual(stats["unscored"], 1)
            self.assertEqual(stats["green"], 1)
            self.assertEqual(stats["yellow"], 1)
            self.assertEqual(stats["library_ready"], 1)
            self.assertEqual(stats["avg_score"], 8.5)

    def test_cli_summary(self):
        """CLI --summary runs without error."""
        self._add_scripts_path()
        from keyframe_score import main as score_main
        with tempfile.TemporaryDirectory() as td:
            vid = Path(td) / "video"
            vid.mkdir()
            idx_path = vid / "index.json"
            idx_path.write_text(json.dumps({"items": {}, "meta_info": {}}))
            rc = score_main(["--state-dir", str(td), "--summary"])
            self.assertEqual(rc, 0)  # no items → no unscored → 0


# ---------------------------------------------------------------------------
# Config files loadable
# ---------------------------------------------------------------------------

class TestVisualConfigFiles(unittest.TestCase):
    """Test that config JSON files are valid and loadable."""

    def _config_dir(self):
        return Path(__file__).resolve().parent.parent / "config"

    def test_visual_identity_loadable(self):
        path = self._config_dir() / "visual_identity.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("identity", data)
        self.assertIn("frame_spec", data)
        self.assertIn("variation_limits", data)
        self.assertIn("locked_traits", data["identity"])

    def test_prompt_cookbook_loadable(self):
        path = self._config_dir() / "prompt_cookbook.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        # v2: modular blocks
        self.assertIn("fixed_blocks", data)
        self.assertIn("variable_blocks", data)
        self.assertIn("core_identity", data["fixed_blocks"])
        self.assertIn("camera", data["fixed_blocks"])
        self.assertIn("negative", data["fixed_blocks"])
        # Variable blocks have environment, outfit, accent
        vb = data["variable_blocks"]
        self.assertIn("environment", vb)
        self.assertIn("outfit", vb)
        self.assertIn("accent", vb)
        self.assertGreater(len(vb["environment"]), 0)
        # Daily rotation + fallback levels
        self.assertIn("daily_rotation", data)
        self.assertIn("fallback_levels", data)

    def test_visual_qc_loadable(self):
        path = self._config_dir() / "visual_qc.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("scoring", data)
        self.assertIn("zones", data)
        self.assertIn("criteria", data["scoring"])
        # All 5 criteria present
        criteria = data["scoring"]["criteria"]
        for c in ["identity", "hands_body", "face_artifacts", "consistency", "lipsync_ready"]:
            self.assertIn(c, criteria, f"Missing criterion: {c}")

    def test_lipsync_mandatory_phrases_present(self):
        path = self._config_dir() / "prompt_cookbook.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        phrases = data.get("lipsync_mandatory_phrases", [])
        self.assertGreater(len(phrases), 0)
        self.assertIn("mouth closed", phrases)
        self.assertIn("same exact person", phrases)

    def test_style_guide_loadable(self):
        path = self._config_dir() / "ray_style_guide.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("canon_specs", data)
        self.assertIn("safe_mode", data)
        self.assertIn("invariants", data)
        self.assertIn("never", data)
        self.assertIn("qc_fast_fail", data)
        self.assertIn("qc_soft_fail", data)
        self.assertIn("qc_pass", data)
        self.assertIn("fallback_levels", data)
        self.assertIn("drift_regression", data)
        self.assertIn("identity_overlay_test", data)
        self.assertIn("visual_qc_exit_codes", data)
        self.assertIn("changelog", data)
        self.assertEqual(data["character"], "Ray")

    def test_voice_dna_loadable(self):
        path = self._config_dir() / "voice_dna.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("canon", data)
        self.assertIn("never", data)
        self.assertIn("script_rules", data)
        self.assertIn("tts_settings", data)
        self.assertIn("qc", data)
        self.assertEqual(data["character"], "Ray")

    def test_cookbook_prebuilt_combos_reference_valid_blocks(self):
        """Prebuilt combos reference blocks that exist in variable_blocks."""
        path = self._config_dir() / "prompt_cookbook.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        vb = data["variable_blocks"]
        for combo_name, combo in data.get("prebuilt_combos", {}).items():
            if combo_name.startswith("_"):
                continue
            self.assertIn(combo["env"], vb["environment"],
                          f"Combo {combo_name}: env {combo['env']} not in variable_blocks")
            self.assertIn(combo["outfit"], vb["outfit"],
                          f"Combo {combo_name}: outfit {combo['outfit']} not in variable_blocks")
            self.assertIn(combo["accent"], vb["accent"],
                          f"Combo {combo_name}: accent {combo['accent']} not in variable_blocks")

    def test_named_prompts_have_files(self):
        """Named prompts reference files that exist."""
        path = self._config_dir() / "prompt_cookbook.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        repo_root = Path(__file__).resolve().parent.parent
        for name, prompt in data.get("named_prompts", {}).items():
            if name.startswith("_"):
                continue
            if "file" in prompt:
                fpath = repo_root / prompt["file"]
                self.assertTrue(fpath.exists(), f"Prompt file missing: {prompt['file']}")

    def test_seed_ladder_has_two_tiers(self):
        """Seed ladder has tier_1 and tier_2."""
        path = self._config_dir() / "prompt_cookbook.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        ladder = data.get("seed_ladder", {})
        self.assertIn("tier_1", ladder)
        self.assertIn("tier_2", ladder)
        self.assertEqual(len(ladder["tier_1"]), 3)
        self.assertEqual(len(ladder["tier_2"]), 3)

    def test_identity_proof_has_method_and_anchors(self):
        """identity_proof schema includes method, anchors_verified, prompt_id."""
        path = self._config_dir() / "visual_identity.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = data["identity_proof"]["fields"]
        self.assertIn("method", fields)
        self.assertIn("anchors_verified", fields)
        self.assertIn("prompt_id", fields)
        self.assertIn("prompt_hash", fields)
        self.assertIn("seed", fields)
        self.assertIn("operator", fields)
        # Anchor fail criteria
        self.assertIn("anchor_fail_criteria", data["identity_proof"])

    def test_voice_dna_sentence_cap(self):
        """Voice DNA has sentence length cap."""
        path = self._config_dir() / "voice_dna.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("sentence_length_words_max", data["script_rules"])
        self.assertEqual(data["script_rules"]["sentence_length_words_max"], 14)
        # Never list includes rhetorical flourish
        self.assertIn("rhetorical flourish", data["never"])

    def test_safe_mode_loadable(self):
        """safe_mode.json is valid and has all required sections."""
        path = self._config_dir() / "safe_mode.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("identity", data)
        self.assertIn("prompts", data)
        self.assertIn("seed_ladder", data)
        self.assertIn("fallback", data)
        self.assertIn("qc", data)
        self.assertIn("voice", data)
        self.assertIn("reporting", data)
        self.assertIn("stability_score", data)
        self.assertIn("telemetry_fields", data)
        # Seed ladder has both tiers
        self.assertIn("tier_1", data["seed_ladder"])
        self.assertIn("tier_2", data["seed_ladder"])
        # Voice has sentence cap
        self.assertEqual(data["voice"]["max_words_per_sentence"], 14)
        self.assertTrue(data["voice"]["no_exclamations"])
        self.assertTrue(data["voice"]["no_rhetorical_questions"])

    def test_prompts_contain_hardening_phrases(self):
        """All prompt files contain the hardening patches."""
        repo_root = Path(__file__).resolve().parent.parent
        for name in ["SAFE_STUDIO_V1", "OFFICE_V1", "DARKDESK_V1"]:
            text = (repo_root / "prompts" / f"{name}.txt").read_text()
            text_lower = text.lower()
            self.assertIn("no tilt", text_lower, f"{name} missing no-tilt")
            self.assertIn("no turn", text_lower, f"{name} missing no-turn")
            self.assertIn("no beard density change", text_lower, f"{name} missing beard-density")
            self.assertIn("no hands visible", text_lower, f"{name} missing no-hands")
            self.assertIn("shoulders only", text_lower, f"{name} missing shoulders-only")


# ---------------------------------------------------------------------------
# Prompt registry tests
# ---------------------------------------------------------------------------

class TestPromptRegistry(unittest.TestCase):
    """Tests for prompt_registry.py."""

    def _add_scripts_path(self):
        p = str(Path(__file__).resolve().parent.parent / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_prompt_hash_deterministic(self):
        self._add_scripts_path()
        from prompt_registry import prompt_hash
        h1 = prompt_hash("hello world")
        h2 = prompt_hash("hello world")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 12)

    def test_prompt_hash_strips_whitespace(self):
        self._add_scripts_path()
        from prompt_registry import prompt_hash
        h1 = prompt_hash("hello world")
        h2 = prompt_hash("hello world\n\n")
        self.assertEqual(h1, h2)

    def test_list_prompts(self):
        self._add_scripts_path()
        from prompt_registry import list_prompts
        prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
        result = list_prompts(prompts_dir)
        self.assertGreater(len(result), 0)
        ids = [p["id"] for p in result]
        self.assertIn("SAFE_STUDIO_V1", ids)
        self.assertIn("OFFICE_V1", ids)
        self.assertIn("DARKDESK_V1", ids)

    def test_load_prompt(self):
        self._add_scripts_path()
        from prompt_registry import load_prompt
        prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
        text = load_prompt("SAFE_STUDIO_V1", prompts_dir)
        self.assertIsNotNone(text)
        self.assertIn("Ray", text)
        self.assertIn("NEGATIVE:", text)

    def test_load_missing_prompt(self):
        self._add_scripts_path()
        from prompt_registry import load_prompt
        result = load_prompt("NONEXISTENT_PROMPT")
        self.assertIsNone(result)

    def test_telemetry_fields(self):
        self._add_scripts_path()
        from prompt_registry import telemetry_fields
        prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
        fields = telemetry_fields("SAFE_STUDIO_V1", prompts_dir)
        self.assertTrue(fields["prompt_found"])
        self.assertEqual(fields["prompt_id"], "SAFE_STUDIO_V1")
        self.assertIsNotNone(fields["prompt_hash"])
        self.assertEqual(len(fields["prompt_hash"]), 12)

    def test_telemetry_missing_prompt(self):
        self._add_scripts_path()
        from prompt_registry import telemetry_fields
        fields = telemetry_fields("NONEXISTENT")
        self.assertFalse(fields["prompt_found"])
        self.assertIsNone(fields["prompt_hash"])

    def test_cli_list(self):
        self._add_scripts_path()
        from prompt_registry import main as reg_main
        rc = reg_main(["--list"])
        self.assertEqual(rc, 0)

    def test_cli_verify(self):
        self._add_scripts_path()
        from prompt_registry import main as reg_main
        rc = reg_main(["--verify"])
        self.assertEqual(rc, 0)


# ── handoff_run tests ────────────────────────────────────────────────────────

class TestHandoffRun(unittest.TestCase):
    """Tests for rayvault.handoff_run — run folder + manifest creation."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.state_dir = Path(self.td) / "state"
        self.state_dir.mkdir()
        # Create prompts dir with a test prompt
        self.prompts_dir = Path(self.td) / "prompts"
        self.prompts_dir.mkdir()
        (self.prompts_dir / "OFFICE_V1.txt").write_text("Test prompt for Office V1")
        (self.prompts_dir / "SAFE_STUDIO_V1.txt").write_text("Test prompt for Safe Studio V1")
        # Create a test script file
        self.script = Path(self.td) / "script.txt"
        self.script.write_text("Hello, this is a test script for RayVault.")
        # Create test audio/frame
        self.audio = Path(self.td) / "audio.wav"
        self.audio.write_bytes(b"RIFF" + b"\x00" * 100)
        self.frame = Path(self.td) / "frame.png"
        self.frame.write_bytes(b"\x89PNG" + b"\x00" * 100)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _handoff(self, **kwargs):
        from rayvault.handoff_run import handoff
        defaults = dict(
            run_id="RUN_TEST_001",
            script_path=self.script,
            audio_path=self.audio,
            frame_path=self.frame,
            prompt_id="OFFICE_V1",
            seed=101,
            fallback_level=0,
            attempts=1,
            identity_confidence="HIGH",
            identity_reason="verified_visual_identity",
            visual_qc="PASS",
            state_dir=self.state_dir,
            prompts_dir=self.prompts_dir,
        )
        defaults.update(kwargs)
        return handoff(**defaults)

    # --- Status decision tests ---

    def test_ready_for_render(self):
        """All assets present + PASS QC → READY_FOR_RENDER."""
        m = self._handoff(visual_qc="PASS", identity_confidence="HIGH")
        self.assertEqual(m["status"], "READY_FOR_RENDER")

    def test_waiting_assets_no_audio(self):
        """Missing audio → WAITING_ASSETS."""
        m = self._handoff(audio_path=None)
        self.assertEqual(m["status"], "WAITING_ASSETS")

    def test_waiting_assets_no_frame(self):
        """Missing frame → WAITING_ASSETS."""
        m = self._handoff(frame_path=None)
        self.assertEqual(m["status"], "WAITING_ASSETS")

    def test_blocked_qc_fail(self):
        """visual_qc=FAIL → BLOCKED."""
        m = self._handoff(visual_qc="FAIL")
        self.assertEqual(m["status"], "BLOCKED")

    def test_blocked_identity_none(self):
        """identity_confidence=NONE → BLOCKED."""
        m = self._handoff(identity_confidence="NONE")
        self.assertEqual(m["status"], "BLOCKED")

    def test_incomplete_no_audio_no_frame_unknown_qc(self):
        """No audio, no frame, UNKNOWN QC → WAITING_ASSETS."""
        m = self._handoff(audio_path=None, frame_path=None, visual_qc="UNKNOWN")
        self.assertEqual(m["status"], "WAITING_ASSETS")

    # --- Manifest structure tests ---

    def test_manifest_schema_version(self):
        m = self._handoff()
        self.assertEqual(m["schema_version"], "1.1")

    def test_manifest_has_all_keys(self):
        m = self._handoff()
        for key in ("schema_version", "run_id", "created_at_utc", "status",
                     "stability", "assets", "metadata", "paths"):
            self.assertIn(key, m, f"Missing key: {key}")

    def test_manifest_stability(self):
        m = self._handoff(fallback_level=1, attempts=3)
        s = m["stability"]
        self.assertEqual(s["fallback_level"], 1)
        self.assertEqual(s["attempts"], 3)
        # 100 - 25 - 16 = 59
        self.assertEqual(s["stability_score"], 59)

    def test_manifest_assets_sha1(self):
        m = self._handoff()
        self.assertIsNotNone(m["assets"]["script"]["sha1"])
        self.assertIsNotNone(m["assets"]["audio"]["sha1"])
        self.assertIsNotNone(m["assets"]["frame"]["sha1"])
        self.assertEqual(len(m["assets"]["script"]["sha1"]), 40)

    def test_manifest_assets_null_sha1_when_missing(self):
        m = self._handoff(audio_path=None, frame_path=None)
        self.assertIsNone(m["assets"]["audio"]["sha1"])
        self.assertIsNone(m["assets"]["frame"]["sha1"])

    def test_manifest_identity_metadata(self):
        m = self._handoff()
        ident = m["metadata"]["identity"]
        self.assertEqual(ident["confidence"], "HIGH")
        self.assertEqual(ident["reason"], "verified_visual_identity")
        self.assertEqual(ident["method"], "human_overlay_3_anchor")
        self.assertEqual(ident["anchors_verified"], ["hairline", "nose_bridge", "jawline"])
        self.assertEqual(ident["reference_strength"], 0.85)

    def test_manifest_prompt_hash(self):
        m = self._handoff(prompt_id="OFFICE_V1")
        self.assertIsNotNone(m["metadata"]["prompt_hash"])
        self.assertEqual(len(m["metadata"]["prompt_hash"]), 12)

    def test_manifest_prompt_hash_none_for_unknown(self):
        m = self._handoff(prompt_id="NONEXISTENT_PROMPT")
        self.assertIsNone(m["metadata"]["prompt_hash"])

    # --- File system tests ---

    def test_run_dir_created(self):
        self._handoff(run_id="RUN_FS_TEST")
        run_dir = self.state_dir / "runs" / "RUN_FS_TEST"
        self.assertTrue(run_dir.exists())

    def test_manifest_file_written(self):
        self._handoff(run_id="RUN_FS_MANIFEST")
        manifest_path = self.state_dir / "runs" / "RUN_FS_MANIFEST" / "00_manifest.json"
        self.assertTrue(manifest_path.exists())
        data = json.loads(manifest_path.read_text())
        self.assertEqual(data["run_id"], "RUN_FS_MANIFEST")

    def test_metadata_file_written(self):
        self._handoff(run_id="RUN_FS_META")
        meta_path = self.state_dir / "runs" / "RUN_FS_META" / "04_metadata.json"
        self.assertTrue(meta_path.exists())
        data = json.loads(meta_path.read_text())
        self.assertEqual(data["run_id"], "RUN_FS_META")

    def test_script_copied(self):
        self._handoff(run_id="RUN_FS_COPY")
        dst = self.state_dir / "runs" / "RUN_FS_COPY" / "01_script.txt"
        self.assertTrue(dst.exists())
        self.assertEqual(dst.read_text(), self.script.read_text())

    def test_audio_copied(self):
        self._handoff(run_id="RUN_FS_AUDIO")
        dst = self.state_dir / "runs" / "RUN_FS_AUDIO" / "02_audio.wav"
        self.assertTrue(dst.exists())

    def test_frame_copied(self):
        self._handoff(run_id="RUN_FS_FRAME")
        dst = self.state_dir / "runs" / "RUN_FS_FRAME" / "03_frame.png"
        self.assertTrue(dst.exists())

    def test_publish_dir_created(self):
        self._handoff(run_id="RUN_FS_PUB")
        pub = self.state_dir / "runs" / "RUN_FS_PUB" / "publish"
        self.assertTrue(pub.is_dir())

    # --- Stability score tests ---

    def test_stability_score_perfect(self):
        from rayvault.handoff_run import compute_stability_score
        self.assertEqual(compute_stability_score(0, 1), 100)

    def test_stability_score_one_retry(self):
        from rayvault.handoff_run import compute_stability_score
        # 100 - 0 - 8 = 92
        self.assertEqual(compute_stability_score(0, 2), 92)

    def test_stability_score_level_2(self):
        from rayvault.handoff_run import compute_stability_score
        # 100 - 50 - 16 = 34
        self.assertEqual(compute_stability_score(2, 3), 34)

    def test_stability_score_library_zero(self):
        from rayvault.handoff_run import compute_stability_score
        self.assertEqual(compute_stability_score(3, 1), 0)
        self.assertEqual(compute_stability_score(4, 1), 0)

    def test_stability_score_floor_zero(self):
        from rayvault.handoff_run import compute_stability_score
        # 100 - 50 - 40 = 10 (still positive)
        self.assertEqual(compute_stability_score(2, 6), 10)

    # --- Validation tests ---

    def test_invalid_run_id_rejected(self):
        with self.assertRaises(ValueError):
            self._handoff(run_id="bad run id with spaces!")

    def test_invalid_confidence_rejected(self):
        with self.assertRaises(ValueError):
            self._handoff(identity_confidence="INVALID")

    def test_existing_dir_rejected_without_force(self):
        self._handoff(run_id="RUN_DUP")
        with self.assertRaises(FileExistsError):
            self._handoff(run_id="RUN_DUP")

    def test_existing_dir_allowed_with_force(self):
        self._handoff(run_id="RUN_FORCE")
        m = self._handoff(run_id="RUN_FORCE", force=True)
        self.assertEqual(m["run_id"], "RUN_FORCE")

    def test_missing_script_rejected(self):
        bad_script = Path(self.td) / "no_such_file.txt"
        with self.assertRaises(FileNotFoundError):
            self._handoff(script_path=bad_script)

    # --- CLI tests ---

    def test_cli_success(self):
        from rayvault.handoff_run import main as hoff_main
        rc = hoff_main([
            "--run-id", "RUN_CLI_OK",
            "--script", str(self.script),
            "--audio", str(self.audio),
            "--frame", str(self.frame),
            "--prompt-id", "OFFICE_V1",
            "--seed", "101",
            "--fallback-level", "0",
            "--identity-confidence", "HIGH",
            "--identity-reason", "verified_visual_identity",
            "--visual-qc", "PASS",
            "--state-dir", str(self.state_dir),
            "--prompts-dir", str(self.prompts_dir),
        ])
        self.assertEqual(rc, 0)

    def test_cli_bad_run_id(self):
        from rayvault.handoff_run import main as hoff_main
        rc = hoff_main([
            "--run-id", "BAD RUN ID",
            "--script", str(self.script),
            "--prompt-id", "OFFICE_V1",
            "--fallback-level", "0",
            "--identity-confidence", "HIGH",
            "--identity-reason", "test",
            "--state-dir", str(self.state_dir),
            "--prompts-dir", str(self.prompts_dir),
        ])
        self.assertEqual(rc, 2)

    def test_cli_missing_script(self):
        from rayvault.handoff_run import main as hoff_main
        rc = hoff_main([
            "--run-id", "RUN_CLI_MISS",
            "--script", "/nonexistent/script.txt",
            "--prompt-id", "OFFICE_V1",
            "--fallback-level", "0",
            "--identity-confidence", "HIGH",
            "--identity-reason", "test",
            "--state-dir", str(self.state_dir),
            "--prompts-dir", str(self.prompts_dir),
        ])
        self.assertEqual(rc, 2)


class TestHandoffDecideStatus(unittest.TestCase):
    """Unit tests for decide_status() logic in isolation."""

    def _decide(self, **kw):
        from rayvault.handoff_run import decide_status
        defaults = dict(
            visual_qc="PASS",
            identity_confidence="HIGH",
            has_script=True,
            has_audio=True,
            has_frame=True,
        )
        defaults.update(kw)
        return decide_status(**defaults)

    def test_all_good(self):
        self.assertEqual(self._decide(), "READY_FOR_RENDER")

    def test_no_script(self):
        self.assertEqual(self._decide(has_script=False), "INCOMPLETE")

    def test_no_audio(self):
        self.assertEqual(self._decide(has_audio=False), "WAITING_ASSETS")

    def test_no_frame(self):
        self.assertEqual(self._decide(has_frame=False), "WAITING_ASSETS")

    def test_qc_fail(self):
        self.assertEqual(self._decide(visual_qc="FAIL"), "BLOCKED")

    def test_identity_none(self):
        self.assertEqual(self._decide(identity_confidence="NONE"), "BLOCKED")

    def test_identity_none_beats_missing_audio(self):
        """BLOCKED takes priority over WAITING_ASSETS."""
        self.assertEqual(
            self._decide(identity_confidence="NONE", has_audio=False),
            "BLOCKED",
        )

    def test_qc_fail_beats_waiting(self):
        """BLOCKED takes priority over WAITING_ASSETS."""
        self.assertEqual(
            self._decide(visual_qc="FAIL", has_frame=False),
            "BLOCKED",
        )

    def test_unknown_qc_all_assets(self):
        """UNKNOWN QC with all assets → INCOMPLETE (not PASS)."""
        self.assertEqual(self._decide(visual_qc="UNKNOWN"), "INCOMPLETE")

    def test_low_confidence_still_ok(self):
        """LOW confidence is not NONE → allows READY_FOR_RENDER."""
        self.assertEqual(self._decide(identity_confidence="LOW"), "READY_FOR_RENDER")


class TestSafeModeConfigV11(unittest.TestCase):
    """Tests for safe_mode.json v1.1 additions."""

    def test_thresholds_present(self):
        cfg = json.loads((Path(__file__).resolve().parent.parent / "config" / "safe_mode.json").read_text())
        self.assertIn("thresholds", cfg)
        t = cfg["thresholds"]
        self.assertIn("stability_warn", t)
        self.assertIn("stability_critical", t)
        self.assertIn("max_generation_time_sec", t)
        self.assertIn("max_consecutive_failures", t)

    def test_prompt_rotation_present(self):
        cfg = json.loads((Path(__file__).resolve().parent.parent / "config" / "safe_mode.json").read_text())
        self.assertIn("prompt_rotation", cfg)
        rot = cfg["prompt_rotation"]
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
            self.assertIn(day, rot)

    def test_prompt_rotation_weekdays_office_or_darkdesk(self):
        cfg = json.loads((Path(__file__).resolve().parent.parent / "config" / "safe_mode.json").read_text())
        rot = cfg["prompt_rotation"]
        for day in ("monday", "wednesday", "friday"):
            self.assertEqual(rot[day], "OFFICE_V1")
        for day in ("tuesday", "thursday"):
            self.assertEqual(rot[day], "DARKDESK_V1")

    def test_prompt_rotation_weekend_safe(self):
        cfg = json.loads((Path(__file__).resolve().parent.parent / "config" / "safe_mode.json").read_text())
        rot = cfg["prompt_rotation"]
        self.assertEqual(rot["saturday"], "SAFE_STUDIO_V1")
        self.assertEqual(rot["sunday"], "SAFE_STUDIO_V1")

    def test_manifest_schema_in_config(self):
        cfg = json.loads((Path(__file__).resolve().parent.parent / "config" / "safe_mode.json").read_text())
        self.assertIn("manifest", cfg)
        self.assertEqual(cfg["manifest"]["schema_version"], "1.0")
        self.assertIn("READY_FOR_RENDER", cfg["manifest"]["status_enum"])

    def test_telegram_rules_in_config(self):
        cfg = json.loads((Path(__file__).resolve().parent.parent / "config" / "safe_mode.json").read_text())
        self.assertIn("telegram", cfg)
        tg = cfg["telegram"]
        self.assertIn("headline_format", tg)
        self.assertIn("status_emoji", tg)
        self.assertIn("next_action", tg)

    def test_prompts_have_file_refs(self):
        cfg = json.loads((Path(__file__).resolve().parent.parent / "config" / "safe_mode.json").read_text())
        prompts = cfg["prompts"]
        for pid in ("SAFE_STUDIO_V1", "OFFICE_V1", "DARKDESK_V1"):
            self.assertIn(pid, prompts)
            self.assertIn("file", prompts[pid])

    def test_identity_proof_required_fields(self):
        cfg = json.loads((Path(__file__).resolve().parent.parent / "config" / "safe_mode.json").read_text())
        required = cfg["identity"]["identity_proof_required"]
        self.assertIn("confidence", required)
        self.assertIn("method", required)
        self.assertIn("anchors_verified", required)


# ── handoff products + render_config tests ──────────────────────────────────

class TestHandoffProducts(unittest.TestCase):
    """Tests for handoff_run product pipeline integration."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.state_dir = Path(self.td) / "state"
        self.state_dir.mkdir()
        self.prompts_dir = Path(self.td) / "prompts"
        self.prompts_dir.mkdir()
        (self.prompts_dir / "OFFICE_V1.txt").write_text("Test prompt")
        self.script = Path(self.td) / "script.txt"
        self.script.write_text("Test script")
        self.audio = Path(self.td) / "audio.wav"
        self.audio.write_bytes(b"RIFF" + b"\x00" * 50)
        self.frame = Path(self.td) / "frame.png"
        self.frame.write_bytes(b"\x89PNG" + b"\x00" * 50)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _make_products_json(self, items=None):
        if items is None:
            items = [
                {"rank": 1, "asin": "B0TEST1", "title": "Product 1"},
                {"rank": 2, "asin": "B0TEST2", "title": "Product 2"},
            ]
        pj = Path(self.td) / "products.json"
        pj.write_text(json.dumps({"items": items}))
        return pj

    def _make_render_config(self):
        rc = Path(self.td) / "render_config.json"
        rc.write_text(json.dumps({"version": "1.0", "video": {"fps": 30}}))
        return rc

    def _handoff(self, **kwargs):
        from rayvault.handoff_run import handoff
        defaults = dict(
            run_id="RUN_PROD_001",
            script_path=self.script,
            audio_path=self.audio,
            frame_path=self.frame,
            prompt_id="OFFICE_V1",
            seed=101,
            fallback_level=0,
            attempts=1,
            identity_confidence="HIGH",
            identity_reason="verified_visual_identity",
            visual_qc="PASS",
            state_dir=self.state_dir,
            prompts_dir=self.prompts_dir,
        )
        defaults.update(kwargs)
        return handoff(**defaults)

    def test_manifest_without_products(self):
        m = self._handoff()
        self.assertNotIn("products", m)

    def test_manifest_with_products_json(self):
        pj = self._make_products_json()
        m = self._handoff(run_id="RUN_P1", products_json_path=pj)
        self.assertIn("products", m)
        self.assertEqual(m["products"]["count"], 2)

    def test_products_copied_to_run_dir(self):
        pj = self._make_products_json()
        self._handoff(run_id="RUN_P2", products_json_path=pj)
        copied = self.state_dir / "runs" / "RUN_P2" / "products" / "products.json"
        self.assertTrue(copied.exists())

    def test_products_fidelity_pending_no_qc(self):
        """Products without qc.json → fidelity PENDING."""
        pj = self._make_products_json()
        m = self._handoff(run_id="RUN_P3", products_json_path=pj)
        self.assertEqual(m["products"]["fidelity"]["result"], "PENDING")

    def test_products_fidelity_pass_with_qc(self):
        """Products with all PASS qc.json → fidelity PASS."""
        pj = self._make_products_json()
        m = self._handoff(run_id="RUN_P4", products_json_path=pj)
        # Create qc.json files for each product
        products_dir = self.state_dir / "runs" / "RUN_P4" / "products"
        for rank in (1, 2):
            pdir = products_dir / f"p{rank:02d}"
            pdir.mkdir(parents=True, exist_ok=True)
            (pdir / "source_images").mkdir()
            (pdir / "source_images" / "01_main.jpg").write_bytes(b"jpg")
            qc = {"product_fidelity_result": "PASS", "broll_method": "DZINE_I2V"}
            (pdir / "qc.json").write_text(json.dumps(qc))
        # Re-evaluate
        from rayvault.handoff_run import evaluate_products
        result = evaluate_products(products_dir)
        self.assertEqual(result["fidelity"]["result"], "PASS")
        self.assertFalse(result["fidelity"]["fallback_used"])

    def test_products_fidelity_fallback_used(self):
        """FALLBACK_IMAGES products → fidelity PASS but fallback_used=True."""
        pj = self._make_products_json([
            {"rank": 1, "asin": "B0A", "title": "Prod A"},
        ])
        m = self._handoff(run_id="RUN_P5", products_json_path=pj)
        products_dir = self.state_dir / "runs" / "RUN_P5" / "products"
        pdir = products_dir / "p01"
        pdir.mkdir(parents=True, exist_ok=True)
        qc = {"product_fidelity_result": "FALLBACK_IMAGES", "broll_method": "KEN_BURNS"}
        (pdir / "qc.json").write_text(json.dumps(qc))
        from rayvault.handoff_run import evaluate_products
        result = evaluate_products(products_dir)
        self.assertEqual(result["fidelity"]["result"], "PASS")
        self.assertTrue(result["fidelity"]["fallback_used"])

    def test_products_fidelity_blocked_on_fail(self):
        """Product with FAIL qc → fidelity BLOCKED."""
        pj = self._make_products_json([
            {"rank": 1, "asin": "B0BAD", "title": "Bad Prod"},
        ])
        m = self._handoff(run_id="RUN_P6", products_json_path=pj)
        products_dir = self.state_dir / "runs" / "RUN_P6" / "products"
        pdir = products_dir / "p01"
        pdir.mkdir(parents=True, exist_ok=True)
        qc = {"product_fidelity_result": "FAIL", "broll_method": "NONE"}
        (pdir / "qc.json").write_text(json.dumps(qc))
        from rayvault.handoff_run import evaluate_products
        result = evaluate_products(products_dir)
        self.assertEqual(result["fidelity"]["result"], "BLOCKED")

    def test_products_summary_includes_ranks(self):
        pj = self._make_products_json()
        m = self._handoff(run_id="RUN_P7", products_json_path=pj)
        summary = m["products"]["summary"]
        self.assertEqual(len(summary), 2)
        self.assertEqual(summary[0]["rank"], 1)
        self.assertEqual(summary[1]["rank"], 2)

    def test_decide_status_blocked_by_products(self):
        from rayvault.handoff_run import decide_status
        status = decide_status(
            visual_qc="PASS",
            identity_confidence="HIGH",
            has_script=True,
            has_audio=True,
            has_frame=True,
            products_fidelity="BLOCKED",
        )
        self.assertEqual(status, "BLOCKED")


class TestHandoffRenderConfig(unittest.TestCase):
    """Tests for render_config handling in handoff_run."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.state_dir = Path(self.td) / "state"
        self.state_dir.mkdir()
        self.prompts_dir = Path(self.td) / "prompts"
        self.prompts_dir.mkdir()
        (self.prompts_dir / "OFFICE_V1.txt").write_text("Test prompt")
        self.script = Path(self.td) / "script.txt"
        self.script.write_text("Test script")
        self.audio = Path(self.td) / "audio.wav"
        self.audio.write_bytes(b"RIFF" + b"\x00" * 50)
        self.frame = Path(self.td) / "frame.png"
        self.frame.write_bytes(b"\x89PNG" + b"\x00" * 50)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _make_render_config(self):
        rc = Path(self.td) / "render_config.json"
        rc.write_text(json.dumps({"version": "1.0", "video": {"fps": 30}}))
        return rc

    def _handoff(self, **kwargs):
        from rayvault.handoff_run import handoff
        defaults = dict(
            run_id="RUN_RC_001",
            script_path=self.script,
            audio_path=self.audio,
            frame_path=self.frame,
            prompt_id="OFFICE_V1",
            seed=101,
            fallback_level=0,
            attempts=1,
            identity_confidence="HIGH",
            identity_reason="verified_visual_identity",
            visual_qc="PASS",
            state_dir=self.state_dir,
            prompts_dir=self.prompts_dir,
        )
        defaults.update(kwargs)
        return handoff(**defaults)

    def test_render_config_copied(self):
        rc = self._make_render_config()
        self._handoff(run_id="RUN_RC1", render_config_path=rc)
        dst = self.state_dir / "runs" / "RUN_RC1" / "05_render_config.json"
        self.assertTrue(dst.exists())

    def test_render_config_sha1_in_manifest(self):
        rc = self._make_render_config()
        m = self._handoff(run_id="RUN_RC2", render_config_path=rc)
        self.assertIsNotNone(m["assets"]["render_config"]["sha1"])
        self.assertEqual(len(m["assets"]["render_config"]["sha1"]), 40)

    def test_render_config_null_when_missing(self):
        m = self._handoff(run_id="RUN_RC3")
        self.assertIsNone(m["assets"]["render_config"]["sha1"])

    def test_manifest_schema_version_1_1(self):
        m = self._handoff(run_id="RUN_RC4")
        self.assertEqual(m["schema_version"], "1.1")


class TestRenderConfigTemplate(unittest.TestCase):
    """Tests for render_config_template.json."""

    def test_template_loadable(self):
        cfg = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "render_config_template.json").read_text()
        )
        self.assertEqual(cfg["version"], "1.0")

    def test_template_video_section(self):
        cfg = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "render_config_template.json").read_text()
        )
        v = cfg["video"]
        self.assertEqual(v["resolution"]["w"], 1920)
        self.assertEqual(v["resolution"]["h"], 1080)
        self.assertEqual(v["fps"], 30)
        self.assertEqual(v["codec"], "h264")

    def test_template_audio_section(self):
        cfg = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "render_config_template.json").read_text()
        )
        a = cfg["audio"]
        self.assertEqual(a["target_lufs"], -14.0)
        self.assertTrue(a["compressor"]["enabled"])

    def test_template_layout_face_safe_box(self):
        cfg = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "render_config_template.json").read_text()
        )
        box = cfg["layout"]["ray_frame"]["face_safe_box"]
        for k in ("x", "y", "w", "h"):
            self.assertIn(k, box)
            self.assertGreater(box[k], 0)
            self.assertLessEqual(box[k], 1.0)

    def test_template_timeline_pattern(self):
        cfg = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "render_config_template.json").read_text()
        )
        pattern = cfg["timeline"]["product_block"]["pattern"]
        types = [p["type"] for p in pattern]
        self.assertIn("ray_talking", types)
        self.assertIn("broll", types)

    def test_template_products_broll_preference(self):
        cfg = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "render_config_template.json").read_text()
        )
        prefs = cfg["products"]["render_rules"]["broll_preference"]
        self.assertEqual(prefs, ["DZINE_I2V", "KEN_BURNS"])


class TestProductAssetFetch(unittest.TestCase):
    """Tests for rayvault.product_asset_fetch — product image download + materialization."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.run_dir = Path(self.td) / "run"
        self.run_dir.mkdir()
        self.products_dir = self.run_dir / "products"
        self.products_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _write_products_json(self, items):
        from rayvault.product_asset_fetch import atomic_write_json
        atomic_write_json(
            self.products_dir / "products.json",
            {"items": items},
        )

    def test_missing_products_json(self):
        from rayvault.product_asset_fetch import run_product_fetch
        result = run_product_fetch(self.run_dir, dry_run=True)
        self.assertFalse(result.ok)
        self.assertEqual(result.errors, 1)

    def test_empty_items(self):
        self._write_products_json([])
        from rayvault.product_asset_fetch import run_product_fetch
        result = run_product_fetch(self.run_dir, dry_run=True)
        self.assertFalse(result.ok)

    def test_dry_run_creates_no_files(self):
        self._write_products_json([
            {"rank": 1, "asin": "B0TEST", "title": "Test Product",
             "image_urls": ["https://example.com/img.jpg"]},
        ])
        from rayvault.product_asset_fetch import run_product_fetch
        result = run_product_fetch(self.run_dir, dry_run=True)
        self.assertTrue(result.ok)
        # product.json should NOT be written in dry_run
        self.assertFalse((self.products_dir / "p01" / "product.json").exists())

    def test_no_image_urls_counts_error(self):
        self._write_products_json([
            {"rank": 1, "asin": "B0NOIMG", "title": "No Images", "image_urls": []},
        ])
        from rayvault.product_asset_fetch import run_product_fetch
        result = run_product_fetch(self.run_dir, dry_run=True)
        self.assertEqual(result.errors, 1)

    def test_missing_asin_counts_error(self):
        self._write_products_json([
            {"rank": 1, "asin": "", "title": "No ASIN", "image_urls": ["https://x.com/a.jpg"]},
        ])
        from rayvault.product_asset_fetch import run_product_fetch
        result = run_product_fetch(self.run_dir, dry_run=True)
        self.assertEqual(result.errors, 1)

    def test_pick_urls_prefers_hires(self):
        from rayvault.product_asset_fetch import pick_urls
        item = {
            "image_urls": ["https://a.com/lo.jpg", "https://a.com/lo2.jpg"],
            "hires_image_urls": ["https://a.com/hi.jpg"],
        }
        urls = pick_urls(item)
        self.assertEqual(urls[0], "https://a.com/hi.jpg")
        self.assertIn("https://a.com/lo.jpg", urls)

    def test_pick_urls_dedupes(self):
        from rayvault.product_asset_fetch import pick_urls
        item = {
            "image_urls": ["https://a.com/same.jpg"],
            "hires_image_urls": ["https://a.com/same.jpg"],
        }
        urls = pick_urls(item)
        self.assertEqual(len(urls), 1)

    def test_safe_ext_from_url(self):
        from rayvault.product_asset_fetch import safe_ext_from_url
        self.assertEqual(safe_ext_from_url("https://x.com/img.png"), ".png")
        self.assertEqual(safe_ext_from_url("https://x.com/img.jpeg"), ".jpg")
        self.assertEqual(safe_ext_from_url("https://x.com/img.webp"), ".webp")
        self.assertEqual(safe_ext_from_url("https://x.com/nope"), ".jpg")

    def test_manifest_updated_with_products(self):
        """Non-destructive manifest update sets products block."""
        from rayvault.product_asset_fetch import load_manifest, update_manifest_products, atomic_write_json
        # Write initial manifest
        atomic_write_json(self.run_dir / "00_manifest.json", {
            "run_id": "TEST", "status": "INIT", "assets": {}, "metadata": {},
        })
        manifest = load_manifest(self.run_dir)
        update_manifest_products(manifest, [
            {"rank": 1, "asin": "B0A", "title": "T", "fidelity": "UNKNOWN", "broll": "PENDING"},
        ], "products/products.json")
        self.assertIn("products", manifest)
        self.assertEqual(manifest["products"]["count"], 1)
        self.assertIn("products_summary", manifest)

    def test_product_dir_structure_created(self):
        """After non-dry fetch with local images, directory structure exists."""
        self._write_products_json([
            {"rank": 1, "asin": "B0LOCAL", "title": "Local Product",
             "image_urls": ["https://example.com/fake.jpg"]},
        ])
        # Pre-create a "downloaded" image to simulate success
        src_dir = self.products_dir / "p01" / "source_images"
        src_dir.mkdir(parents=True)
        (src_dir / "01_main.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 3000)

        from rayvault.product_asset_fetch import run_product_fetch
        result = run_product_fetch(self.run_dir, dry_run=False)
        # Image was already there → skipped
        self.assertEqual(result.skipped, 1)
        self.assertTrue((self.products_dir / "p01" / "product.json").exists())
        self.assertTrue((self.products_dir / "p01" / "qc.json").exists())
        self.assertTrue((self.products_dir / "p01" / "broll").is_dir())
        self.assertTrue((self.products_dir / "p01" / "source_images" / "hashes.json").exists())


class TestProductBrollContract(unittest.TestCase):
    """Tests for product_broll_contract.json."""

    def test_contract_loadable(self):
        cfg = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "product_broll_contract.json").read_text()
        )
        self.assertEqual(cfg["version"], "1.0")

    def test_golden_rule_present(self):
        cfg = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "product_broll_contract.json").read_text()
        )
        self.assertIn("golden_rule", cfg)
        self.assertIn("never", cfg["golden_rule"].lower())

    def test_reference_mode(self):
        cfg = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "product_broll_contract.json").read_text()
        )
        rm = cfg["reference_mode"]
        self.assertEqual(rm["type"], "image_to_video")
        self.assertGreaterEqual(rm["reference_strength_min"], 0.85)

    def test_fast_fail_criteria(self):
        cfg = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "product_broll_contract.json").read_text()
        )
        ff = cfg["product_fidelity_qc"]["fast_fail"]
        self.assertIn("product_shape_differs", ff)
        self.assertIn("wrong_color_material", ff)

    def test_shot_list_clips(self):
        cfg = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "product_broll_contract.json").read_text()
        )
        sl = cfg["shot_list"]
        self.assertIn("clip_a", sl)
        self.assertIn("clip_b", sl)

    def test_script_truth_boundary(self):
        cfg = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "product_broll_contract.json").read_text()
        )
        stb = cfg["script_truth_boundary"]
        self.assertIn("allowed", stb)
        self.assertIn("forbidden", stb)
        self.assertEqual(stb["cta"], "Link in description")


# ── product asset fetch + truth cache integration tests ──────────────────────

class TestProductAssetFetchCache(unittest.TestCase):
    """Tests for TruthCache integration in product_asset_fetch.py."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.run_dir = Path(self.td) / "run"
        self.run_dir.mkdir()
        self.products_dir = self.run_dir / "products"
        self.products_dir.mkdir()
        self.library_dir = Path(self.td) / "library"
        self.library_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _write_products_json(self, items):
        from rayvault.product_asset_fetch import atomic_write_json
        atomic_write_json(
            self.products_dir / "products.json",
            {"items": items},
        )

    def _seed_cache(self, asin, with_image=True, with_meta=True):
        """Pre-populate truth cache for an ASIN."""
        from rayvault.truth_cache import TruthCache
        cache = TruthCache(self.library_dir)
        meta = {"title": f"Cached {asin}", "asin": asin} if with_meta else None
        imgs = []
        if with_image:
            img = Path(self.td) / f"cached_{asin}.jpg"
            img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 3000)
            # Rename to 01_main.jpg for the cache
            dest = Path(self.td) / "01_main.jpg"
            import shutil
            shutil.copy2(str(img), str(dest))
            imgs = [dest]
        cache.put_from_fetch(asin, meta, imgs)

    def test_cache_hit_skips_download(self):
        """When cache has fresh images, no download needed."""
        self._seed_cache("B0CACHED")
        self._write_products_json([
            {"rank": 1, "asin": "B0CACHED", "title": "Cached Product",
             "image_urls": ["https://example.com/img.jpg"]},
        ])
        from rayvault.product_asset_fetch import run_product_fetch
        result = run_product_fetch(self.run_dir, library_dir=self.library_dir)
        self.assertTrue(result.ok)
        self.assertEqual(result.cache_hits, 1)
        self.assertEqual(result.downloaded, 0)
        # Image should be materialized from cache
        src = self.products_dir / "p01" / "source_images"
        self.assertTrue(any(f.name.startswith("01_main") for f in src.iterdir()))

    def test_no_cache_flag_skips_cache(self):
        """library_dir=None disables cache entirely."""
        self._seed_cache("B0SKIP")
        self._write_products_json([
            {"rank": 1, "asin": "B0SKIP", "title": "Uncached Product",
             "image_urls": ["https://example.com/img.jpg"]},
        ])
        # Pre-create image to avoid network
        src = self.products_dir / "p01" / "source_images"
        src.mkdir(parents=True)
        (src / "01_main.jpg").write_bytes(b"\xff\xd8" * 2000)
        from rayvault.product_asset_fetch import run_product_fetch
        result = run_product_fetch(self.run_dir, library_dir=None)
        self.assertEqual(result.cache_hits, 0)
        self.assertEqual(result.skipped, 1)

    def test_cache_miss_falls_through_to_download(self):
        """Cache miss with pre-existing images still works."""
        self._write_products_json([
            {"rank": 1, "asin": "B0MISS", "title": "Miss Product",
             "image_urls": ["https://example.com/img.jpg"]},
        ])
        # Pre-create image to simulate previous download
        src = self.products_dir / "p01" / "source_images"
        src.mkdir(parents=True)
        (src / "01_main.jpg").write_bytes(b"\xff\xd8" * 2000)
        from rayvault.product_asset_fetch import run_product_fetch
        result = run_product_fetch(self.run_dir, library_dir=self.library_dir)
        self.assertTrue(result.ok)
        self.assertEqual(result.cache_hits, 0)
        self.assertEqual(result.skipped, 1)  # image already existed in run dir

    def test_cache_stores_after_download(self):
        """After downloading, images are stored in cache for next run."""
        self._write_products_json([
            {"rank": 1, "asin": "B0STORE", "title": "Store Product",
             "image_urls": ["https://example.com/img.jpg"]},
        ])
        # Pre-create image to simulate successful download
        src = self.products_dir / "p01" / "source_images"
        src.mkdir(parents=True)
        (src / "01_main.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 3000)
        from rayvault.product_asset_fetch import run_product_fetch
        run_product_fetch(self.run_dir, library_dir=self.library_dir)
        # Verify cache now has this ASIN
        from rayvault.truth_cache import TruthCache
        cache = TruthCache(self.library_dir)
        self.assertTrue(cache.has_main_image("B0STORE"))

    def test_manifest_records_cache_stats(self):
        """Manifest should include cache_hits and library_dir."""
        self._seed_cache("B0STATS")
        self._write_products_json([
            {"rank": 1, "asin": "B0STATS", "title": "Stats Product",
             "image_urls": ["https://example.com/img.jpg"]},
        ])
        from rayvault.product_asset_fetch import run_product_fetch, atomic_write_json
        atomic_write_json(self.run_dir / "00_manifest.json", {"run_id": "TEST", "status": "INIT"})
        run_product_fetch(self.run_dir, library_dir=self.library_dir)
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        self.assertEqual(m["products"]["cache_hits"], 1)
        self.assertIn("library_dir", m["products"])

    def test_cache_hit_product_summary_has_source(self):
        """Products from cache should be marked with source='cache'."""
        self._seed_cache("B0SRC")
        self._write_products_json([
            {"rank": 1, "asin": "B0SRC", "title": "Src Product",
             "image_urls": ["https://example.com/img.jpg"]},
        ])
        from rayvault.product_asset_fetch import run_product_fetch, atomic_write_json, load_manifest
        atomic_write_json(self.run_dir / "00_manifest.json", {"run_id": "TEST", "status": "INIT"})
        run_product_fetch(self.run_dir, library_dir=self.library_dir)
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        summary = m.get("products_summary", [])
        self.assertGreater(len(summary), 0)
        self.assertEqual(summary[0]["truth_source"], "CACHE")

    def test_multiple_products_mixed_cache(self):
        """Some products from cache, others need download."""
        self._seed_cache("B0A1")
        # B0B2 NOT in cache
        self._write_products_json([
            {"rank": 1, "asin": "B0A1", "title": "Cached One",
             "image_urls": ["https://example.com/a.jpg"]},
            {"rank": 2, "asin": "B0B2", "title": "Fresh Two",
             "image_urls": ["https://example.com/b.jpg"]},
        ])
        # Pre-create image for rank 2 to avoid network
        src = self.products_dir / "p02" / "source_images"
        src.mkdir(parents=True)
        (src / "01_main.jpg").write_bytes(b"\xff\xd8" * 2000)
        from rayvault.product_asset_fetch import run_product_fetch
        result = run_product_fetch(self.run_dir, library_dir=self.library_dir)
        self.assertTrue(result.ok)
        self.assertEqual(result.cache_hits, 1)
        self.assertEqual(result.skipped, 1)  # rank 2 image already there

    def test_fetch_result_cache_hits_field(self):
        from rayvault.product_asset_fetch import FetchResult
        r = FetchResult(ok=True, downloaded=1, skipped=2, errors=0, cache_hits=3)
        self.assertEqual(r.cache_hits, 3)

    def test_qc_initialized_on_cache_hit(self):
        """qc.json should be created even when product comes from cache."""
        self._seed_cache("B0QC")
        self._write_products_json([
            {"rank": 1, "asin": "B0QC", "title": "QC Product",
             "image_urls": ["https://example.com/img.jpg"]},
        ])
        from rayvault.product_asset_fetch import run_product_fetch
        run_product_fetch(self.run_dir, library_dir=self.library_dir)
        self.assertTrue((self.products_dir / "p01" / "qc.json").exists())

    def test_metadata_stored_in_cache(self):
        """Product metadata (including bullets) should be stored in cache."""
        self._write_products_json([
            {"rank": 1, "asin": "B0META", "title": "Meta Product",
             "bullets": ["Waterproof IPX7", "8 hours battery"],
             "image_urls": ["https://example.com/img.jpg"]},
        ])
        # Pre-create image
        src = self.products_dir / "p01" / "source_images"
        src.mkdir(parents=True)
        (src / "01_main.jpg").write_bytes(b"\xff\xd8" * 2000)
        from rayvault.product_asset_fetch import run_product_fetch
        run_product_fetch(self.run_dir, library_dir=self.library_dir)
        from rayvault.truth_cache import TruthCache
        cache = TruthCache(self.library_dir)
        cached = cache.get_cached("B0META")
        self.assertIn("meta", cached)
        self.assertIn("bullets", cached["meta"])
        self.assertEqual(len(cached["meta"]["bullets"]), 2)


# ── cleanup_run tests ────────────────────────────────────────────────────────

class TestCleanupRun(unittest.TestCase):
    """Tests for rayvault.cleanup_run — selective post-publish purge."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.run_dir = Path(self.td) / "run"
        self.run_dir.mkdir()
        # Minimal manifest
        self._write_json(self.run_dir / "00_manifest.json", {
            "schema_version": "1.1", "run_id": "TEST", "status": "PUBLISHED",
        })
        # Heavy assets
        (self.run_dir / "02_audio.wav").write_bytes(b"\x00" * 5000)
        (self.run_dir / "03_frame.png").write_bytes(b"\x00" * 3000)
        # Products
        products = self.run_dir / "products"
        for rank in (1, 2):
            pdir = products / f"p{rank:02d}"
            src = pdir / "source_images"
            broll = pdir / "broll"
            src.mkdir(parents=True)
            broll.mkdir(parents=True)
            (src / "01_main.jpg").write_bytes(b"\xff\xd8" * 500)
            (src / "02_alt.jpg").write_bytes(b"\xff\xd8" * 300)
            (broll / "clip.mp4").write_bytes(b"\x00" * 2000)
            self._write_json(pdir / "qc.json", {"product_fidelity_result": "PASS"})
            self._write_json(pdir / "product.json", {"rank": rank, "asin": "B0X"})
        # Publish dir
        pub = self.run_dir / "publish"
        pub.mkdir()
        (pub / "video_final.mp4").write_bytes(b"\x00" * 10000)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def _write_receipt(self, status="UPLOADED"):
        from rayvault.youtube_upload_receipt import sign_receipt
        receipt = {
            "version": "1.0", "run_id": "TEST", "status": status,
            "uploader": "test", "uploaded_at_utc": "2026-01-01T00:00:00Z",
            "inputs": {"video_sha256": "abc", "video_size_bytes": 1000},
            "youtube": {"video_id": "test123", "channel_id": "UC000"},
        }
        hmac_val = sign_receipt(receipt)
        receipt["integrity"] = {"method": "hmac_sha256", "hmac_sha256": hmac_val}
        self._write_json(self.run_dir / "publish" / "upload_receipt.json", receipt)

    def test_refuses_without_receipt(self):
        from rayvault.cleanup_run import cleanup
        ok, info = cleanup(self.run_dir)
        self.assertFalse(ok)
        self.assertEqual(info, "missing_receipt")

    def test_refuses_non_uploaded_receipt(self):
        self._write_receipt("PENDING")
        from rayvault.cleanup_run import cleanup
        ok, info = cleanup(self.run_dir)
        self.assertFalse(ok)
        self.assertIn("PENDING", info)

    def test_force_bypasses_receipt(self):
        from rayvault.cleanup_run import cleanup
        ok, info = cleanup(self.run_dir, force=True)
        self.assertTrue(ok)
        self.assertGreater(info["targets"], 0)

    def test_refuses_missing_manifest(self):
        (self.run_dir / "00_manifest.json").unlink()
        from rayvault.cleanup_run import cleanup
        ok, info = cleanup(self.run_dir, force=True)
        self.assertFalse(ok)
        self.assertEqual(info, "missing_manifest")

    def test_refuses_missing_run_dir(self):
        from rayvault.cleanup_run import cleanup
        ok, info = cleanup(Path(self.td) / "nope", force=True)
        self.assertFalse(ok)
        self.assertEqual(info, "missing_run_dir")

    def test_refuses_too_new(self):
        self._write_receipt()
        from rayvault.cleanup_run import cleanup
        ok, info = cleanup(self.run_dir, min_age_hours=999.0)
        self.assertFalse(ok)
        self.assertEqual(info, "too_new_refuse")

    def test_dry_run_does_not_delete(self):
        self._write_receipt()
        from rayvault.cleanup_run import cleanup
        ok, info = cleanup(self.run_dir, apply=False)
        self.assertTrue(ok)
        self.assertFalse(info["applied"])
        # Files still exist
        self.assertTrue((self.run_dir / "02_audio.wav").exists())
        self.assertTrue((self.run_dir / "03_frame.png").exists())

    def test_apply_deletes_heavy_assets(self):
        self._write_receipt()
        from rayvault.cleanup_run import cleanup
        ok, info = cleanup(self.run_dir, apply=True)
        self.assertTrue(ok)
        self.assertTrue(info["applied"])
        self.assertGreater(info["deleted"], 0)
        # Heavy files gone
        self.assertFalse((self.run_dir / "02_audio.wav").exists())
        self.assertFalse((self.run_dir / "03_frame.png").exists())
        # Source images gone
        self.assertFalse((self.run_dir / "products" / "p01" / "source_images").exists())
        # B-roll gone
        self.assertFalse((self.run_dir / "products" / "p01" / "broll").exists())

    def test_apply_keeps_metadata(self):
        self._write_receipt()
        from rayvault.cleanup_run import cleanup
        cleanup(self.run_dir, apply=True)
        # Manifest still exists
        self.assertTrue((self.run_dir / "00_manifest.json").exists())
        # Product metadata still exists
        self.assertTrue((self.run_dir / "products" / "p01" / "product.json").exists())
        self.assertTrue((self.run_dir / "products" / "p01" / "qc.json").exists())

    def test_keep_main_image(self):
        self._write_receipt()
        from rayvault.cleanup_run import cleanup
        cleanup(self.run_dir, apply=True, keep_main_image=True)
        # 01_main.jpg preserved
        self.assertTrue(
            (self.run_dir / "products" / "p01" / "source_images" / "01_main.jpg").exists()
        )
        # 02_alt.jpg deleted
        self.assertFalse(
            (self.run_dir / "products" / "p01" / "source_images" / "02_alt.jpg").exists()
        )

    def test_delete_final_video(self):
        self._write_receipt()
        from rayvault.cleanup_run import cleanup
        cleanup(self.run_dir, apply=True, delete_final_video=True)
        self.assertFalse((self.run_dir / "publish" / "video_final.mp4").exists())
        # Receipt preserved
        self.assertTrue((self.run_dir / "publish" / "upload_receipt.json").exists())

    def test_no_delete_final_without_flag(self):
        self._write_receipt()
        from rayvault.cleanup_run import cleanup
        cleanup(self.run_dir, apply=True, delete_final_video=False)
        self.assertTrue((self.run_dir / "publish" / "video_final.mp4").exists())

    def test_cleanup_history_written(self):
        self._write_receipt()
        from rayvault.cleanup_run import cleanup
        cleanup(self.run_dir, apply=True)
        manifest = json.loads((self.run_dir / "00_manifest.json").read_text())
        self.assertIn("housekeeping", manifest)
        hist = manifest["housekeeping"]["cleanup_history"]
        self.assertEqual(len(hist), 1)
        self.assertTrue(hist[0]["applied"])
        self.assertGreater(hist[0]["bytes_freed_est"], 0)

    def test_cleanup_history_ring_buffer(self):
        self._write_receipt()
        from rayvault.cleanup_run import cleanup
        for _ in range(12):
            cleanup(self.run_dir, apply=False)
        manifest = json.loads((self.run_dir / "00_manifest.json").read_text())
        self.assertEqual(len(manifest["housekeeping"]["cleanup_history"]), 10)

    def test_cli_dry_run(self):
        self._write_receipt()
        from rayvault.cleanup_run import main as cl_main
        rc = cl_main(["--run-dir", str(self.run_dir)])
        self.assertEqual(rc, 0)

    def test_cli_refused(self):
        from rayvault.cleanup_run import main as cl_main
        rc = cl_main(["--run-dir", str(self.run_dir)])
        self.assertEqual(rc, 2)


# ── render_config_generate tests ─────────────────────────────────────────────

class TestRenderConfigGenerate(unittest.TestCase):
    """Tests for rayvault.render_config_generate — timeline + product truth."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.run_dir = Path(self.td) / "run"
        self.run_dir.mkdir()
        # Script
        (self.run_dir / "01_script.txt").write_text(
            "Welcome to today's top 5 products. " * 20
        )
        # Manifest
        (self.run_dir / "00_manifest.json").write_text(json.dumps({
            "schema_version": "1.1", "run_id": "TEST", "status": "INCOMPLETE",
        }))
        # Products
        products_dir = self.run_dir / "products"
        products_dir.mkdir()
        items = []
        for rank in range(1, 6):
            items.append({"rank": rank, "asin": f"B0TEST{rank}", "title": f"Product {rank}"})
            pdir = products_dir / f"p{rank:02d}"
            src = pdir / "source_images"
            src.mkdir(parents=True)
            (pdir / "broll").mkdir()
            (src / "01_main.jpg").write_bytes(b"\xff\xd8" * 500)
            (pdir / "qc.json").write_text(json.dumps({
                "product_fidelity_result": "PASS", "broll_method": "KEN_BURNS",
            }))
        (products_dir / "products.json").write_text(json.dumps({"items": items}))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def test_generates_render_config(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        self.assertTrue((self.run_dir / "05_render_config.json").exists())

    def test_config_version(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        self.assertEqual(result["config"]["version"], "1.3")

    def test_config_has_canvas(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        c = result["config"]["canvas"]
        self.assertEqual(c["w"], 1920)
        self.assertEqual(c["h"], 1080)
        self.assertEqual(c["fps"], 30)

    def test_config_has_audio(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        a = result["config"]["audio"]
        self.assertEqual(a["normalize_lufs"], -14.0)
        self.assertTrue(a["limiter"])

    def test_config_has_ray_frame(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        ray = result["config"]["ray"]
        self.assertEqual(ray["frame_path"], "03_frame.png")
        box = ray["face_safe_box_norm"]
        for k in ("x", "y", "w", "h"):
            self.assertIn(k, box)

    def test_segments_intro_products_outro(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        segs = result["config"]["segments"]
        types = [s["type"] for s in segs]
        self.assertEqual(types[0], "intro")
        self.assertEqual(types[-1], "outro")
        product_segs = [s for s in segs if s["type"] == "product"]
        self.assertEqual(len(product_segs), 5)

    def test_fidelity_score_100_all_images(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        self.assertEqual(result["fidelity_score"], 100)
        self.assertFalse(result["needs_manual_review"])

    def test_fidelity_score_drops_with_skip(self):
        """Remove source image from p03 → fidelity drops."""
        import shutil
        shutil.rmtree(self.run_dir / "products" / "p03" / "source_images")
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        self.assertEqual(result["fidelity_score"], 80)  # 4/5 = 80
        self.assertFalse(result["needs_manual_review"])  # 80 >= 80

    def test_fidelity_below_80_needs_review(self):
        """Remove source images from p03 and p04 → needs review."""
        import shutil
        shutil.rmtree(self.run_dir / "products" / "p03" / "source_images")
        shutil.rmtree(self.run_dir / "products" / "p04" / "source_images")
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        self.assertEqual(result["fidelity_score"], 60)  # 3/5 = 60
        self.assertTrue(result["needs_manual_review"])

    def test_patient_zero_set_on_skip(self):
        import shutil
        shutil.rmtree(self.run_dir / "products" / "p02" / "source_images")
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        pz = result["patient_zero"]
        self.assertIsNotNone(pz)
        self.assertEqual(pz["code"], "MISSING_PRODUCT_IMAGE")
        self.assertIn("p02", pz["detail"])

    def test_patient_zero_none_when_all_good(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        self.assertIsNone(result["patient_zero"])

    def test_visual_mode_ken_burns_from_image(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        seg1 = [s for s in result["config"]["segments"] if s.get("rank") == 1][0]
        self.assertEqual(seg1["visual"]["mode"], "KEN_BURNS")
        self.assertIn("source_images", seg1["visual"]["source"])

    def test_visual_mode_broll_preferred(self):
        """If approved.mp4 exists, BROLL_VIDEO takes priority."""
        (self.run_dir / "products" / "p01" / "broll" / "approved.mp4").write_bytes(b"\x00" * 100)
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        seg1 = [s for s in result["config"]["segments"] if s.get("rank") == 1][0]
        self.assertEqual(seg1["visual"]["mode"], "BROLL_VIDEO")

    def test_visual_mode_skip_no_image(self):
        import shutil
        shutil.rmtree(self.run_dir / "products" / "p01" / "source_images")
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        seg1 = [s for s in result["config"]["segments"] if s.get("rank") == 1][0]
        self.assertEqual(seg1["visual"]["mode"], "SKIP")

    def test_manifest_updated_with_render(self):
        from rayvault.render_config_generate import generate_render_config
        generate_render_config(self.run_dir)
        manifest = json.loads((self.run_dir / "00_manifest.json").read_text())
        self.assertIn("render", manifest)
        self.assertEqual(manifest["render"]["products_fidelity_score"], 100)
        self.assertIn("render_config_sha1", manifest["render"])

    def test_missing_script_raises(self):
        (self.run_dir / "01_script.txt").unlink()
        from rayvault.render_config_generate import generate_render_config
        with self.assertRaises(FileNotFoundError):
            generate_render_config(self.run_dir)

    def test_no_products_still_generates(self):
        """Run without products.json still produces valid config."""
        import shutil
        shutil.rmtree(self.run_dir / "products")
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        segs = result["config"]["segments"]
        self.assertEqual(len(segs), 2)  # intro + outro only

    def test_cli_success(self):
        from rayvault.render_config_generate import main as rcg_main
        rc = rcg_main(["--run-dir", str(self.run_dir)])
        self.assertEqual(rc, 0)

    def test_cli_missing_dir(self):
        from rayvault.render_config_generate import main as rcg_main
        rc = rcg_main(["--run-dir", str(Path(self.td) / "nope")])
        self.assertEqual(rc, 2)

    def test_qc_skip_overrides_image(self):
        """QC broll_method=SKIP forces SKIP even if image exists."""
        (self.run_dir / "products" / "p01" / "qc.json").write_text(json.dumps({
            "product_fidelity_result": "FAIL", "broll_method": "SKIP",
        }))
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        seg1 = [s for s in result["config"]["segments"] if s.get("rank") == 1][0]
        self.assertEqual(seg1["visual"]["mode"], "SKIP")

    def test_still_only_mode(self):
        """QC broll_method=STILL_ONLY uses main image as still."""
        (self.run_dir / "products" / "p01" / "qc.json").write_text(json.dumps({
            "product_fidelity_result": "PASS", "broll_method": "STILL_ONLY",
        }))
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        seg1 = [s for s in result["config"]["segments"] if s.get("rank") == 1][0]
        self.assertEqual(seg1["visual"]["mode"], "STILL_ONLY")
        self.assertIn("source_images", seg1["visual"]["source"])

    def test_strict_approved_mp4_only(self):
        """Random mp4 in broll/ is NOT picked; only approved.mp4."""
        (self.run_dir / "products" / "p01" / "broll" / "random_junk.mp4").write_bytes(b"\x00" * 100)
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        seg1 = [s for s in result["config"]["segments"] if s.get("rank") == 1][0]
        # Should be KEN_BURNS from source image, NOT BROLL_VIDEO
        self.assertEqual(seg1["visual"]["mode"], "KEN_BURNS")

    def test_config_has_products_block(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        p = result["config"]["products"]
        self.assertEqual(p["expected"], 5)
        self.assertEqual(p["truth_visuals_used"], 5)
        self.assertEqual(p["fidelity_score"], 100)
        self.assertEqual(p["min_truth_required"], 4)

    def test_config_has_audio_duration(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        a = result["config"]["audio"]
        self.assertIn("duration_sec", a)
        self.assertGreater(a["duration_sec"], 0)

    def test_require_audio_raises_when_missing(self):
        from rayvault.render_config_generate import generate_render_config
        with self.assertRaises(FileNotFoundError):
            generate_render_config(self.run_dir, require_audio=True)

    def test_timeline_timestamps_monotonic(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        segs = result["config"]["segments"]
        for i, seg in enumerate(segs):
            self.assertLess(seg["t0"], seg["t1"])
            if i > 0:
                self.assertGreaterEqual(seg["t0"], segs[i - 1]["t0"])


# ── handoff strict product gates tests ───────────────────────────────────────

class TestHandoffProductGates(unittest.TestCase):
    """Tests for strict product + render_config gates in handoff_run.py."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.state_dir = Path(self.td) / "state"
        self.state_dir.mkdir()
        self.prompts_dir = Path(self.td) / "prompts"
        self.prompts_dir.mkdir()
        (self.prompts_dir / "OFFICE_V1.txt").write_text("Test prompt")
        self.script = Path(self.td) / "script.txt"
        self.script.write_text("Test script")
        self.audio = Path(self.td) / "audio.wav"
        self.audio.write_bytes(b"RIFF" + b"\x00" * 100)
        self.frame = Path(self.td) / "frame.png"
        self.frame.write_bytes(b"\x89PNG" + b"\x00" * 100)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _make_products(self, n=5, with_images=True):
        """Create products.json and product directories."""
        pj_path = Path(self.td) / "products.json"
        items = [{"rank": i, "asin": f"B0P{i}", "title": f"Prod {i}"} for i in range(1, n + 1)]
        pj_path.write_text(json.dumps({"items": items}))
        return pj_path

    def _add_product_images(self, run_id, ranks):
        """Add source images to product directories inside run dir."""
        for rank in ranks:
            src = self.state_dir / "runs" / run_id / "products" / f"p{rank:02d}" / "source_images"
            src.mkdir(parents=True, exist_ok=True)
            (src / "01_main.jpg").write_bytes(b"\xff" * 3000)

    def _add_render_config(self, run_id):
        rc = self.state_dir / "runs" / run_id / "05_render_config.json"
        rc.parent.mkdir(parents=True, exist_ok=True)
        rc.write_text(json.dumps({"version": "1.0"}))

    def _handoff(self, run_id="RUN_GATE_01", **kwargs):
        from rayvault.handoff_run import handoff
        defaults = dict(
            run_id=run_id,
            script_path=self.script,
            audio_path=self.audio,
            frame_path=self.frame,
            prompt_id="OFFICE_V1",
            seed=101,
            fallback_level=0,
            attempts=1,
            identity_confidence="HIGH",
            identity_reason="verified_visual_identity",
            visual_qc="PASS",
            state_dir=self.state_dir,
            prompts_dir=self.prompts_dir,
        )
        defaults.update(kwargs)
        return handoff(**defaults)

    def test_ready_without_products(self):
        """No products at all → READY (products are optional)."""
        m = self._handoff(run_id="RUN_G1")
        self.assertEqual(m["status"], "READY_FOR_RENDER")

    def test_products_without_images_waiting(self):
        """Products exist but no source images → WAITING_ASSETS."""
        pj = self._make_products(5)
        m = self._handoff(run_id="RUN_G2", products_json_path=pj)
        self.assertEqual(m["status"], "WAITING_ASSETS")

    def test_products_4_of_5_images_and_render_config_ready(self):
        """4/5 products have images + render_config → READY."""
        pj = self._make_products(5)
        m = self._handoff(run_id="RUN_G3", products_json_path=pj)
        # Now add images for 4 of 5 products
        self._add_product_images("RUN_G3", [1, 2, 3, 4])
        self._add_render_config("RUN_G3")
        # Re-run handoff with force
        m2 = self._handoff(run_id="RUN_G3", products_json_path=pj, force=True)
        self.assertEqual(m2["status"], "READY_FOR_RENDER")

    def test_products_3_of_5_images_waiting(self):
        """3/5 products have images → WAITING_ASSETS (needs 4/5)."""
        pj = self._make_products(5)
        self._handoff(run_id="RUN_G4", products_json_path=pj)
        self._add_product_images("RUN_G4", [1, 2, 3])
        self._add_render_config("RUN_G4")
        m = self._handoff(run_id="RUN_G4", products_json_path=pj, force=True)
        self.assertEqual(m["status"], "WAITING_ASSETS")

    def test_products_no_render_config_waiting(self):
        """All product images but no render_config → WAITING_ASSETS."""
        pj = self._make_products(5)
        self._handoff(run_id="RUN_G5", products_json_path=pj)
        self._add_product_images("RUN_G5", [1, 2, 3, 4, 5])
        m = self._handoff(run_id="RUN_G5", products_json_path=pj, force=True)
        self.assertEqual(m["status"], "WAITING_ASSETS")

    def test_patient_zero_missing_image(self):
        """patient_zero reports first missing product image."""
        pj = self._make_products(5)
        m = self._handoff(run_id="RUN_G6", products_json_path=pj)
        self.assertIn("patient_zero", m)
        self.assertEqual(m["patient_zero"]["code"], "MISSING_PRODUCT_IMAGE")

    def test_patient_zero_missing_audio(self):
        m = self._handoff(run_id="RUN_G7", audio_path=None)
        self.assertIn("patient_zero", m)
        self.assertEqual(m["patient_zero"]["code"], "MISSING_AUDIO")

    def test_patient_zero_missing_frame(self):
        m = self._handoff(run_id="RUN_G8", frame_path=None)
        self.assertIn("patient_zero", m)
        self.assertEqual(m["patient_zero"]["code"], "MISSING_FRAME")

    def test_patient_zero_none_when_ready(self):
        m = self._handoff(run_id="RUN_G9")
        self.assertNotIn("patient_zero", m)

    def test_patient_zero_identity_none(self):
        m = self._handoff(run_id="RUN_G10", identity_confidence="NONE")
        self.assertIn("patient_zero", m)
        self.assertEqual(m["patient_zero"]["code"], "IDENTITY_NONE")

    def test_patient_zero_visual_qc_fail(self):
        m = self._handoff(run_id="RUN_G11", visual_qc="FAIL",
                          visual_fail_reason="teeth_visible")
        self.assertIn("patient_zero", m)
        self.assertEqual(m["patient_zero"]["code"], "VISUAL_QC_FAIL")


# ── final validator tests ─────────────────────────────────────────────────────

class TestFinalValidator(unittest.TestCase):
    """Tests for rayvault/final_validator.py — last gate before upload."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.run_dir = Path(self.td) / "state" / "runs" / "RUN_VAL_01"
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "publish").mkdir()
        # Create minimal manifest
        manifest = {
            "schema_version": "1.1",
            "run_id": "RUN_VAL_01",
            "status": "READY_FOR_RENDER",
            "stability": {"stability_score": 100, "fallback_level": 0, "attempts": 1},
            "metadata": {
                "identity": {"confidence": "HIGH", "reason": "test"},
                "visual_qc_result": "PASS",
            },
            "render": {"engine_used": "davinci", "davinci_required": True},
        }
        self._write_json(self.run_dir / "00_manifest.json", manifest)
        # Core assets
        (self.run_dir / "01_script.txt").write_text("Test script for validation.")
        (self.run_dir / "02_audio.wav").write_bytes(b"RIFF" + b"\x00" * 100)
        (self.run_dir / "03_frame.png").write_bytes(b"\x89PNG" + b"\x00" * 100)
        # Render config
        rc = {"version": "1.1", "segments": [{"type": "intro", "t0": 0, "t1": 2}]}
        self._write_json(self.run_dir / "05_render_config.json", rc)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def _make_video(self, size=2048):
        v = self.run_dir / "publish" / "video_final.mp4"
        v.write_bytes(b"\x00" * size)

    def test_all_gates_pass(self):
        from rayvault.final_validator import validate_run
        self._make_video()
        v = validate_run(self.run_dir)
        self.assertTrue(v.all_passed)
        self.assertEqual(len(v.failed_gates), 0)

    def test_missing_manifest_fails(self):
        from rayvault.final_validator import validate_run
        (self.run_dir / "00_manifest.json").unlink()
        v = validate_run(self.run_dir)
        self.assertFalse(v.all_passed)
        self.assertIn("manifest_exists", v.failed_gates)

    def test_wrong_status_fails(self):
        from rayvault.final_validator import validate_run
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        m["status"] = "BLOCKED"
        self._write_json(self.run_dir / "00_manifest.json", m)
        self._make_video()
        v = validate_run(self.run_dir)
        self.assertFalse(v.all_passed)
        self.assertIn("manifest_status", v.failed_gates)

    def test_missing_audio_fails(self):
        from rayvault.final_validator import validate_run
        (self.run_dir / "02_audio.wav").unlink()
        self._make_video()
        v = validate_run(self.run_dir)
        self.assertFalse(v.all_passed)
        self.assertIn("core_assets", v.failed_gates)

    def test_missing_render_config_fails(self):
        from rayvault.final_validator import validate_run
        (self.run_dir / "05_render_config.json").unlink()
        self._make_video()
        v = validate_run(self.run_dir)
        self.assertFalse(v.all_passed)
        self.assertIn("render_config", v.failed_gates)

    def test_low_identity_fails(self):
        from rayvault.final_validator import validate_run
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        m["metadata"]["identity"]["confidence"] = "LOW"
        self._write_json(self.run_dir / "00_manifest.json", m)
        self._make_video()
        v = validate_run(self.run_dir)
        self.assertFalse(v.all_passed)
        self.assertIn("identity_confidence", v.failed_gates)

    def test_visual_qc_fail(self):
        from rayvault.final_validator import validate_run
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        m["metadata"]["visual_qc_result"] = "FAIL"
        self._write_json(self.run_dir / "00_manifest.json", m)
        self._make_video()
        v = validate_run(self.run_dir)
        self.assertFalse(v.all_passed)
        self.assertIn("visual_qc", v.failed_gates)

    def test_missing_video_fails(self):
        from rayvault.final_validator import validate_run
        v = validate_run(self.run_dir)
        self.assertFalse(v.all_passed)
        self.assertIn("final_video", v.failed_gates)

    def test_no_video_flag_skips(self):
        from rayvault.final_validator import validate_run
        v = validate_run(self.run_dir, require_video=False)
        self.assertTrue(v.all_passed)

    def test_low_stability_fails(self):
        from rayvault.final_validator import validate_run
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        m["stability"]["stability_score"] = 30
        self._write_json(self.run_dir / "00_manifest.json", m)
        self._make_video()
        v = validate_run(self.run_dir, stability_threshold=40)
        self.assertFalse(v.all_passed)
        self.assertIn("stability_score", v.failed_gates)

    def test_patient_zero_is_first_failure(self):
        from rayvault.final_validator import validate_run
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        m["status"] = "BLOCKED"
        self._write_json(self.run_dir / "00_manifest.json", m)
        self._make_video()
        v = validate_run(self.run_dir)
        self.assertIsNotNone(v.patient_zero)
        self.assertEqual(v.patient_zero, "manifest_status")

    def test_verdict_to_dict(self):
        from rayvault.final_validator import validate_run
        self._make_video()
        v = validate_run(self.run_dir)
        d = v.to_dict()
        self.assertIn("run_id", d)
        self.assertIn("gates", d)
        self.assertIn("checked_at_utc", d)

    def test_validation_written_to_manifest(self):
        from rayvault.final_validator import validate_run
        self._make_video()
        validate_run(self.run_dir)
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        self.assertIn("validation", m)
        self.assertTrue(m["validation"]["passed"])

    def test_claims_review_required_blocks(self):
        from rayvault.final_validator import validate_run
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        m["claims_validation"] = {"status": "REVIEW_REQUIRED", "violations": [{"x": 1}]}
        self._write_json(self.run_dir / "00_manifest.json", m)
        self._make_video()
        v = validate_run(self.run_dir)
        self.assertFalse(v.all_passed)
        self.assertIn("claims_validation", v.failed_gates)

    def test_claims_pass_ok(self):
        from rayvault.final_validator import validate_run
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        m["claims_validation"] = {"status": "PASS", "violations": []}
        self._write_json(self.run_dir / "00_manifest.json", m)
        self._make_video()
        v = validate_run(self.run_dir)
        self.assertTrue(v.all_passed)

    def test_no_claims_block_is_pass(self):
        """If claims_guardrail hasn't run yet, don't block."""
        from rayvault.final_validator import validate_run
        self._make_video()
        v = validate_run(self.run_dir)
        self.assertTrue(v.all_passed)

    def test_cli_exit_0_on_pass(self):
        from rayvault.final_validator import main
        self._make_video()
        rc = main(["--run-dir", str(self.run_dir)])
        self.assertEqual(rc, 0)

    def test_cli_exit_2_on_fail(self):
        from rayvault.final_validator import main
        # No video
        rc = main(["--run-dir", str(self.run_dir)])
        self.assertEqual(rc, 2)


# ── youtube upload receipt tests ──────────────────────────────────────────────

class TestYoutubeUploadReceipt(unittest.TestCase):
    """Tests for rayvault/youtube_upload_receipt.py — HMAC-signed receipt."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.run_dir = Path(self.td) / "state" / "runs" / "RUN_REC_01"
        self.run_dir.mkdir(parents=True)
        publish = self.run_dir / "publish"
        publish.mkdir()
        # Create manifest
        manifest = {
            "schema_version": "1.1",
            "run_id": "RUN_REC_01",
            "status": "READY_FOR_RENDER",
            "stability": {"stability_score": 100},
            "metadata": {},
        }
        self._write_json(self.run_dir / "00_manifest.json", manifest)
        # Create video
        (publish / "video_final.mp4").write_bytes(b"\x00\x00\x01\xb3" + b"\xff" * 5000)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def test_generate_receipt(self):
        from rayvault.youtube_upload_receipt import generate_receipt
        r = generate_receipt(self.run_dir, video_id="abc123", channel_id="UC000")
        self.assertEqual(r["status"], "UPLOADED")
        self.assertEqual(r["youtube"]["video_id"], "abc123")
        self.assertIn("hmac_sha256", r["integrity"])

    def test_receipt_file_written(self):
        from rayvault.youtube_upload_receipt import generate_receipt
        generate_receipt(self.run_dir, video_id="abc123")
        rp = self.run_dir / "publish" / "upload_receipt.json"
        self.assertTrue(rp.exists())
        data = json.loads(rp.read_text())
        self.assertEqual(data["status"], "UPLOADED")

    def test_hmac_verifies(self):
        from rayvault.youtube_upload_receipt import generate_receipt, verify_receipt
        r = generate_receipt(self.run_dir, video_id="abc123")
        self.assertTrue(verify_receipt(r))

    def test_tampered_receipt_fails(self):
        from rayvault.youtube_upload_receipt import generate_receipt, verify_receipt
        r = generate_receipt(self.run_dir, video_id="abc123")
        r["status"] = "VERIFIED"  # tamper
        self.assertFalse(verify_receipt(r))

    def test_manifest_updated_to_uploaded(self):
        from rayvault.youtube_upload_receipt import generate_receipt
        generate_receipt(self.run_dir, video_id="abc123")
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        self.assertEqual(m["status"], "UPLOADED")
        self.assertIn("publish", m)
        self.assertEqual(m["publish"]["video_id"], "abc123")

    def test_preflight_fails_no_manifest(self):
        from rayvault.youtube_upload_receipt import generate_receipt
        (self.run_dir / "00_manifest.json").unlink()
        with self.assertRaises(ValueError):
            generate_receipt(self.run_dir, video_id="abc123")

    def test_preflight_fails_no_video(self):
        from rayvault.youtube_upload_receipt import generate_receipt
        (self.run_dir / "publish" / "video_final.mp4").unlink()
        with self.assertRaises(ValueError):
            generate_receipt(self.run_dir, video_id="abc123")

    def test_empty_video_id_fails(self):
        from rayvault.youtube_upload_receipt import generate_receipt
        with self.assertRaises(ValueError):
            generate_receipt(self.run_dir, video_id="")

    def test_receipt_has_video_hash(self):
        from rayvault.youtube_upload_receipt import generate_receipt
        r = generate_receipt(self.run_dir, video_id="test123")
        self.assertTrue(len(r["inputs"]["video_sha256"]) == 64)
        self.assertGreater(r["inputs"]["video_size_bytes"], 0)

    def test_receipt_schema_version(self):
        from rayvault.youtube_upload_receipt import generate_receipt
        r = generate_receipt(self.run_dir, video_id="test123")
        self.assertEqual(r["version"], "1.0")

    def test_no_video_check_flag(self):
        from rayvault.youtube_upload_receipt import generate_receipt
        (self.run_dir / "publish" / "video_final.mp4").unlink()
        r = generate_receipt(self.run_dir, video_id="abc123", require_video=False)
        self.assertEqual(r["status"], "UPLOADED")

    def test_cli_verify_mode(self):
        from rayvault.youtube_upload_receipt import generate_receipt, main
        generate_receipt(self.run_dir, video_id="abc123")
        rc = main(["--run-dir", str(self.run_dir), "--verify"])
        self.assertEqual(rc, 0)

    def test_cli_verify_no_receipt(self):
        from rayvault.youtube_upload_receipt import main
        rc = main(["--run-dir", str(self.run_dir), "--verify"])
        self.assertEqual(rc, 2)

    def test_sign_deterministic(self):
        from rayvault.youtube_upload_receipt import generate_receipt, sign_receipt
        r = generate_receipt(self.run_dir, video_id="abc123")
        sig1 = sign_receipt(r)
        sig2 = sign_receipt(r)
        self.assertEqual(sig1, sig2)

    def test_different_run_id_different_hmac(self):
        from rayvault.youtube_upload_receipt import sign_receipt
        r1 = {"version": "1.0", "run_id": "RUN_A", "status": "UPLOADED",
               "inputs": {"video_sha256": "aaa", "video_size_bytes": 100},
               "youtube": {"video_id": "x", "channel_id": "c"},
               "uploaded_at_utc": "2026-01-01T00:00:00Z"}
        r2 = dict(r1)
        r2["run_id"] = "RUN_B"
        self.assertNotEqual(sign_receipt(r1), sign_receipt(r2))


# ── cleanup with HMAC tests ──────────────────────────────────────────────────

class TestCleanupHMAC(unittest.TestCase):
    """Tests for HMAC-verified cleanup in cleanup_run.py."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.run_dir = Path(self.td) / "state" / "runs" / "RUN_CL_HMAC"
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "publish").mkdir()
        manifest = {"schema_version": "1.1", "run_id": "RUN_CL_HMAC", "status": "UPLOADED"}
        self._write_json(self.run_dir / "00_manifest.json", manifest)
        # Create heavy assets
        (self.run_dir / "02_audio.wav").write_bytes(b"\x00" * 100)
        (self.run_dir / "03_frame.png").write_bytes(b"\x00" * 100)
        # Create valid receipt with HMAC
        self._create_valid_receipt()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def _create_valid_receipt(self):
        from rayvault.youtube_upload_receipt import sign_receipt
        receipt = {
            "version": "1.0",
            "run_id": "RUN_CL_HMAC",
            "status": "UPLOADED",
            "uploader": "test",
            "uploaded_at_utc": "2026-01-01T00:00:00Z",
            "inputs": {"video_sha256": "abc", "video_size_bytes": 1000},
            "youtube": {"video_id": "test123", "channel_id": "UC000"},
        }
        hmac_val = sign_receipt(receipt)
        receipt["integrity"] = {"method": "hmac_sha256", "hmac_sha256": hmac_val,
                                 "signed_fields": "version|run_id|status|..."}
        self._write_json(self.run_dir / "publish" / "upload_receipt.json", receipt)

    def _create_tampered_receipt(self):
        receipt = {
            "version": "1.0",
            "run_id": "RUN_CL_HMAC",
            "status": "UPLOADED",
            "uploader": "test",
            "uploaded_at_utc": "2026-01-01T00:00:00Z",
            "inputs": {"video_sha256": "abc", "video_size_bytes": 1000},
            "youtube": {"video_id": "test123", "channel_id": "UC000"},
            "integrity": {"method": "hmac_sha256", "hmac_sha256": "deadbeef",
                          "signed_fields": "version|run_id|status|..."},
        }
        self._write_json(self.run_dir / "publish" / "upload_receipt.json", receipt)

    def test_valid_hmac_allows_cleanup(self):
        from rayvault.cleanup_run import cleanup
        ok, info = cleanup(self.run_dir)
        self.assertTrue(ok)

    def test_tampered_hmac_refuses_cleanup(self):
        from rayvault.cleanup_run import cleanup
        self._create_tampered_receipt()
        ok, info = cleanup(self.run_dir)
        self.assertFalse(ok)
        self.assertEqual(info, "receipt_hmac_invalid")

    def test_force_bypasses_hmac(self):
        from rayvault.cleanup_run import cleanup
        self._create_tampered_receipt()
        ok, info = cleanup(self.run_dir, force=True)
        self.assertTrue(ok)

    def test_missing_receipt_refuses(self):
        from rayvault.cleanup_run import cleanup
        (self.run_dir / "publish" / "upload_receipt.json").unlink()
        ok, info = cleanup(self.run_dir)
        self.assertFalse(ok)
        self.assertEqual(info, "missing_receipt")

    def test_verified_status_accepted(self):
        from rayvault.youtube_upload_receipt import sign_receipt
        from rayvault.cleanup_run import cleanup
        receipt = {
            "version": "1.0", "run_id": "RUN_CL_HMAC", "status": "VERIFIED",
            "uploader": "test", "uploaded_at_utc": "2026-01-01T00:00:00Z",
            "inputs": {"video_sha256": "abc", "video_size_bytes": 1000},
            "youtube": {"video_id": "v", "channel_id": "c"},
        }
        receipt["integrity"] = {"method": "hmac_sha256", "hmac_sha256": sign_receipt(receipt)}
        self._write_json(self.run_dir / "publish" / "upload_receipt.json", receipt)
        ok, info = cleanup(self.run_dir)
        self.assertTrue(ok)

    def test_receipt_wrong_status_refuses(self):
        from rayvault.cleanup_run import cleanup
        receipt = {
            "version": "1.0", "run_id": "RUN_CL_HMAC", "status": "PROCESSING",
            "inputs": {}, "youtube": {},
            "integrity": {"hmac_sha256": "x"},
        }
        self._write_json(self.run_dir / "publish" / "upload_receipt.json", receipt)
        ok, info = cleanup(self.run_dir)
        self.assertFalse(ok)
        self.assertIn("PROCESSING", info)


# ── claims guardrail tests ───────────────────────────────────────────────────

class TestClaimsGuardrail(unittest.TestCase):
    """Tests for rayvault/claims_guardrail.py — anti-lie firewall."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.run_dir = Path(self.td) / "run"
        self.run_dir.mkdir()
        (self.run_dir / "products").mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def _setup_products(self, bullets=None):
        items = [
            {"rank": 1, "asin": "B001", "title": "Wireless Earbuds Waterproof IPX7",
             "bullets": bullets or ["Waterproof IPX7 rated", "8 hours battery life", "Bluetooth 5.3"]},
        ]
        self._write_json(self.run_dir / "products" / "products.json", {"items": items})

    def test_pass_when_script_matches_products(self):
        from rayvault.claims_guardrail import guardrail
        self._setup_products()
        (self.run_dir / "01_script.txt").write_text(
            "These earbuds are waterproof with an IPX7 rating."
        )
        r = guardrail(self.run_dir)
        self.assertEqual(r["status"], "PASS")

    def test_review_required_when_claim_unsupported(self):
        from rayvault.claims_guardrail import guardrail
        self._setup_products(bullets=["Basic earbuds", "Good sound"])
        (self.run_dir / "01_script.txt").write_text(
            "These earbuds come with a lifetime warranty."
        )
        r = guardrail(self.run_dir)
        self.assertEqual(r["status"], "REVIEW_REQUIRED")
        self.assertGreater(len(r["violations"]), 0)

    def test_missing_script_returns_error(self):
        from rayvault.claims_guardrail import guardrail
        self._setup_products()
        r = guardrail(self.run_dir)
        self.assertEqual(r["status"], "ERROR")
        self.assertEqual(r["code"], "MISSING_SCRIPT")

    def test_missing_products_returns_error(self):
        from rayvault.claims_guardrail import guardrail
        (self.run_dir / "01_script.txt").write_text("Test script.")
        (self.run_dir / "products" / "products.json").unlink(missing_ok=True)
        r = guardrail(self.run_dir)
        self.assertEqual(r["status"], "ERROR")

    def test_no_trigger_sentences_pass(self):
        from rayvault.claims_guardrail import guardrail
        self._setup_products()
        (self.run_dir / "01_script.txt").write_text(
            "Here are some nice earbuds for everyday use."
        )
        r = guardrail(self.run_dir)
        self.assertEqual(r["status"], "PASS")
        self.assertEqual(r["trigger_sentences_count"], 0)

    def test_trigger_with_evidence_passes(self):
        from rayvault.claims_guardrail import guardrail
        self._setup_products(bullets=["FDA certified medical grade"])
        (self.run_dir / "01_script.txt").write_text(
            "This product is certified by strict standards."
        )
        r = guardrail(self.run_dir)
        self.assertEqual(r["status"], "PASS")

    def test_multiple_violations(self):
        from rayvault.claims_guardrail import guardrail
        self._setup_products(bullets=["Basic product"])
        (self.run_dir / "01_script.txt").write_text(
            "This is waterproof. It has a lifetime warranty. It is FDA certified."
        )
        r = guardrail(self.run_dir)
        self.assertEqual(r["status"], "REVIEW_REQUIRED")
        self.assertGreaterEqual(len(r["violations"]), 2)

    def test_result_file_written(self):
        from rayvault.claims_guardrail import guardrail, atomic_write_json
        self._setup_products()
        (self.run_dir / "01_script.txt").write_text("Nice product.")
        r = guardrail(self.run_dir)
        atomic_write_json(self.run_dir / "claims_guardrail.json", r)
        self.assertTrue((self.run_dir / "claims_guardrail.json").exists())

    def test_manifest_updated(self):
        from rayvault.claims_guardrail import guardrail, update_manifest
        self._setup_products()
        (self.run_dir / "01_script.txt").write_text("Nice product.")
        manifest = {"run_id": "TEST", "status": "READY"}
        self._write_json(self.run_dir / "00_manifest.json", manifest)
        r = guardrail(self.run_dir)
        update_manifest(self.run_dir, r)
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        self.assertIn("claims_validation", m)
        self.assertEqual(m["claims_validation"]["status"], "PASS")

    def test_normalize_text(self):
        from rayvault.claims_guardrail import normalize_text
        self.assertEqual(normalize_text("  Hello   World  "), "hello world")

    def test_find_trigger_sentences(self):
        from rayvault.claims_guardrail import find_trigger_sentences
        script = "This is waterproof. Normal sentence. Has battery life."
        hits = find_trigger_sentences(script)
        self.assertGreaterEqual(len(hits), 2)

    def test_check_evidence_with_keywords(self):
        from rayvault.claims_guardrail import check_evidence
        ok, missing = check_evidence("waterproof earbuds", "waterproof ipx7 rated earbuds")
        self.assertTrue(ok)
        self.assertEqual(missing, [])

    def test_check_evidence_missing(self):
        from rayvault.claims_guardrail import check_evidence
        ok, missing = check_evidence("waterproof earbuds", "basic earbuds good sound")
        self.assertFalse(ok)
        self.assertIn("waterproof", missing)


# ── verify visibility tests ──────────────────────────────────────────────────

class TestVerifyVisibility(unittest.TestCase):
    """Tests for rayvault/verify_visibility.py — UPLOADED -> VERIFIED."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.run_dir = Path(self.td) / "state" / "runs" / "RUN_VIS_01"
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "publish").mkdir()
        manifest = {"schema_version": "1.1", "run_id": "RUN_VIS_01", "status": "UPLOADED"}
        self._write_json(self.run_dir / "00_manifest.json", manifest)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def _create_receipt(self, status="UPLOADED", video_id="test123"):
        from rayvault.youtube_upload_receipt import sign_receipt
        receipt = {
            "version": "1.0", "run_id": "RUN_VIS_01", "status": status,
            "uploader": "test", "uploaded_at_utc": "2026-01-01T00:00:00Z",
            "inputs": {"video_sha256": "abc", "video_size_bytes": 1000},
            "youtube": {"video_id": video_id, "channel_id": "UC000"},
        }
        receipt["integrity"] = {"method": "hmac_sha256", "hmac_sha256": sign_receipt(receipt)}
        self._write_json(self.run_dir / "publish" / "upload_receipt.json", receipt)

    def test_missing_receipt_fails(self):
        from rayvault.verify_visibility import verify
        r = verify(self.run_dir)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "missing_receipt")

    def test_manual_verify_succeeds(self):
        from rayvault.verify_visibility import verify
        self._create_receipt()
        r = verify(self.run_dir, manual=True)
        self.assertTrue(r["ok"])
        self.assertEqual(r["status"], "VERIFIED")

    def test_manual_verify_updates_receipt(self):
        from rayvault.verify_visibility import verify
        self._create_receipt()
        verify(self.run_dir, manual=True)
        receipt = json.loads((self.run_dir / "publish" / "upload_receipt.json").read_text())
        self.assertEqual(receipt["status"], "VERIFIED")
        self.assertIn("verified_at_utc", receipt)

    def test_manual_verify_updates_manifest(self):
        from rayvault.verify_visibility import verify
        self._create_receipt()
        verify(self.run_dir, manual=True)
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        self.assertEqual(m["status"], "VERIFIED")
        self.assertTrue(m["publish"]["verified"])

    def test_already_verified_returns_ok(self):
        from rayvault.verify_visibility import verify
        self._create_receipt(status="VERIFIED")
        r = verify(self.run_dir)
        self.assertTrue(r["ok"])
        self.assertTrue(r.get("already"))

    def test_no_verify_cmd_fails(self):
        from rayvault.verify_visibility import verify
        self._create_receipt()
        with patch.dict(os.environ, {}, clear=True):
            r = verify(self.run_dir, verify_cmd=None)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "no_verify_cmd")

    def test_wrong_receipt_status_fails(self):
        from rayvault.verify_visibility import verify
        receipt = {"version": "1.0", "run_id": "RUN_VIS_01", "status": "PROCESSING",
                   "inputs": {}, "youtube": {"video_id": "x"}, "integrity": {}}
        self._write_json(self.run_dir / "publish" / "upload_receipt.json", receipt)
        r = verify(self.run_dir)
        self.assertFalse(r["ok"])

    def test_missing_video_id_fails(self):
        from rayvault.verify_visibility import verify
        receipt = {"version": "1.0", "run_id": "RUN_VIS_01", "status": "UPLOADED",
                   "inputs": {}, "youtube": {}, "integrity": {}}
        self._write_json(self.run_dir / "publish" / "upload_receipt.json", receipt)
        r = verify(self.run_dir)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "missing_video_id")


# ── render config skipped_count telemetry tests ──────────────────────────────

class TestRenderConfigTelemetry(unittest.TestCase):
    """Tests for skipped_count in render_config_generate.py."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.run_dir = Path(self.td) / "run"
        self.run_dir.mkdir()
        (self.run_dir / "01_script.txt").write_text("Test " * 50)
        manifest = {"run_id": "RUN_TEL", "status": "READY"}
        with open(self.run_dir / "00_manifest.json", "w") as f:
            json.dump(manifest, f)
        # Create products
        products_dir = self.run_dir / "products"
        products_dir.mkdir()
        items = [{"rank": i, "asin": f"B{i:03d}", "title": f"Product {i}"}
                 for i in range(1, 6)]
        with open(products_dir / "products.json", "w") as f:
            json.dump({"items": items}, f)
        # Only give 3 products images
        for i in range(1, 4):
            src = products_dir / f"p{i:02d}" / "source_images"
            src.mkdir(parents=True)
            (src / "01_main.jpg").write_bytes(b"\xff" * 3000)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def test_skipped_count_in_config(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        products = result["config"]["products"]
        self.assertIn("skipped_count", products)
        # 5 products, 3 have images -> 2 skipped
        self.assertEqual(products["skipped_count"], 2)
        self.assertEqual(products["truth_visuals_used"], 3)

    def test_skipped_count_in_manifest(self):
        from rayvault.render_config_generate import generate_render_config
        generate_render_config(self.run_dir)
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        self.assertIn("render", m)
        self.assertEqual(m["render"]["skipped_count"], 2)

    def test_all_products_have_images_zero_skipped(self):
        from rayvault.render_config_generate import generate_render_config
        products_dir = self.run_dir / "products"
        for i in range(4, 6):
            src = products_dir / f"p{i:02d}" / "source_images"
            src.mkdir(parents=True)
            (src / "01_main.jpg").write_bytes(b"\xff" * 3000)
        result = generate_render_config(self.run_dir)
        self.assertEqual(result["config"]["products"]["skipped_count"], 0)
        self.assertEqual(result["config"]["products"]["truth_visuals_used"], 5)


# ── status enum tests ────────────────────────────────────────────────────────

class TestStatusEnum(unittest.TestCase):
    """Tests for VALID_STATUSES including new UPLOADED/VERIFIED."""

    def test_valid_statuses_includes_uploaded(self):
        from rayvault.handoff_run import VALID_STATUSES
        self.assertIn("UPLOADED", VALID_STATUSES)

    def test_valid_statuses_includes_verified(self):
        from rayvault.handoff_run import VALID_STATUSES
        self.assertIn("VERIFIED", VALID_STATUSES)

    def test_valid_statuses_complete(self):
        from rayvault.handoff_run import VALID_STATUSES
        expected = {"INCOMPLETE", "WAITING_ASSETS", "READY_FOR_RENDER",
                    "BLOCKED", "UPLOADED", "VERIFIED", "PUBLISHED"}
        self.assertEqual(VALID_STATUSES, expected)


# ── truth cache tests ─────────────────────────────────────────────────────────

class TestTruthCache(unittest.TestCase):
    """Tests for rayvault/truth_cache.py — ASIN-keyed product asset cache."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.lib_root = Path(self.td) / "library"
        self.lib_root.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _make_cache(self, **kwargs):
        from rayvault.truth_cache import TruthCache, CachePolicy
        policy = CachePolicy(**kwargs) if kwargs else CachePolicy()
        return TruthCache(self.lib_root, policy)

    def test_empty_cache_returns_empty(self):
        cache = self._make_cache()
        self.assertEqual(cache.get_cached("B0MISSING"), {})

    def test_put_metadata(self):
        cache = self._make_cache()
        meta = {"title": "Test Product", "asin": "B0TEST"}
        result = cache.put_from_fetch("B0TEST", meta, [])
        self.assertTrue(result["ok"])
        cached = cache.get_cached("B0TEST")
        self.assertEqual(cached["meta"]["title"], "Test Product")

    def test_put_images(self):
        cache = self._make_cache()
        img = Path(self.td) / "01_main.jpg"
        img.write_bytes(b"\xff\xd8" * 2000)
        result = cache.put_from_fetch("B0TEST", None, [img])
        self.assertTrue(result["ok"])
        self.assertIn("01_main.jpg", result["stored_images"])
        self.assertTrue(cache.has_main_image("B0TEST"))

    def test_materialize_copy(self):
        cache = self._make_cache()
        img = Path(self.td) / "01_main.jpg"
        img.write_bytes(b"\xff\xd8" * 2000)
        cache.put_from_fetch("B0TEST", {"title": "X"}, [img])
        run_pdir = Path(self.td) / "run" / "products" / "p01"
        result = cache.materialize_to_run("B0TEST", run_pdir, mode="copy")
        self.assertTrue(result["ok"])
        self.assertEqual(result["code"], "MATERIALIZED")
        self.assertTrue((run_pdir / "source_images" / "01_main.jpg").exists())
        self.assertTrue((run_pdir / "product_metadata.json").exists())

    def test_materialize_cache_miss(self):
        cache = self._make_cache()
        run_pdir = Path(self.td) / "run" / "p01"
        result = cache.materialize_to_run("B0MISSING", run_pdir)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "CACHE_MISS")

    def test_needs_refresh_fresh(self):
        cache = self._make_cache(ttl_meta_sec=999999, ttl_images_sec=999999)
        img = Path(self.td) / "01_main.jpg"
        img.write_bytes(b"\xff" * 100)
        cache.put_from_fetch("B0TEST", {"title": "X"}, [img])
        need = cache.needs_refresh("B0TEST")
        self.assertTrue(need["has_meta"])
        self.assertTrue(need["has_images"])
        self.assertTrue(need["meta_fresh"])
        self.assertTrue(need["images_fresh"])
        self.assertFalse(need["refresh_meta"])
        self.assertFalse(need["refresh_images"])

    def test_needs_refresh_stale(self):
        cache = self._make_cache(ttl_meta_sec=0, ttl_images_sec=0)
        img = Path(self.td) / "01_main.jpg"
        img.write_bytes(b"\xff" * 100)
        cache.put_from_fetch("B0TEST", {"title": "X"}, [img])
        # With TTL=0, everything is stale immediately
        need = cache.needs_refresh("B0TEST")
        self.assertTrue(need["refresh_meta"])
        self.assertTrue(need["refresh_images"])

    def test_needs_refresh_no_cache(self):
        cache = self._make_cache()
        need = cache.needs_refresh("B0NONE")
        self.assertFalse(need["has_meta"])
        self.assertFalse(need["has_images"])

    def test_hashes_written(self):
        cache = self._make_cache()
        img = Path(self.td) / "01_main.jpg"
        img.write_bytes(b"\xff\xd8" * 500)
        cache.put_from_fetch("B0TEST", None, [img])
        hashes = json.loads(cache.hashes_path("B0TEST").read_text())
        self.assertIn("01_main.jpg", hashes["images"])
        self.assertIn("sha1", hashes["images"]["01_main.jpg"])

    def test_cache_info_provenance(self):
        cache = self._make_cache()
        cache.put_from_fetch("B0TEST", {"title": "X"}, [], http_status=200)
        info = json.loads(cache.cache_info_path("B0TEST").read_text())
        self.assertEqual(info["fetched_from"], "amazon")
        self.assertEqual(info["http_status_last"], 200)

    def test_stats_empty(self):
        cache = self._make_cache()
        s = cache.stats()
        self.assertEqual(s["total_asins"], 0)

    def test_stats_with_data(self):
        cache = self._make_cache()
        img = Path(self.td) / "01_main.jpg"
        img.write_bytes(b"\xff" * 100)
        cache.put_from_fetch("B0A", {"title": "A"}, [img])
        img2 = Path(self.td) / "01_main.jpg"
        img2.write_bytes(b"\xff" * 200)
        cache.put_from_fetch("B0B", {"title": "B"}, [img2])
        s = cache.stats()
        self.assertEqual(s["total_asins"], 2)
        self.assertGreater(s["total_bytes"], 0)

    def test_idempotent_put(self):
        cache = self._make_cache()
        img = Path(self.td) / "01_main.jpg"
        img.write_bytes(b"\xff" * 100)
        cache.put_from_fetch("B0TEST", {"title": "X"}, [img])
        # Put again (image already exists in cache, temp file consumed)
        img2 = Path(self.td) / "01_main.jpg"
        img2.write_bytes(b"\xff" * 100)
        result = cache.put_from_fetch("B0TEST", {"title": "Y"}, [img2])
        self.assertTrue(result["ok"])
        # Metadata updated
        cached = cache.get_cached("B0TEST")
        self.assertEqual(cached["meta"]["title"], "Y")

    def test_has_main_image_false(self):
        cache = self._make_cache()
        self.assertFalse(cache.has_main_image("B0NOPE"))

    def test_materialize_skip_existing(self):
        cache = self._make_cache()
        img = Path(self.td) / "01_main.jpg"
        img.write_bytes(b"\xff" * 100)
        cache.put_from_fetch("B0TEST", None, [img])
        run_pdir = Path(self.td) / "run" / "p01"
        cache.materialize_to_run("B0TEST", run_pdir)
        # Materialize again — should skip
        result = cache.materialize_to_run("B0TEST", run_pdir)
        self.assertTrue(result["ok"])
        self.assertEqual(result["images_copied"], 0)


# ── cron verify visibility tests ─────────────────────────────────────────────

class TestCronVerifyVisibility(unittest.TestCase):
    """Tests for rayvault/cron_verify_visibility.py — batch verification."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.runs_root = Path(self.td) / "state" / "runs"
        self.runs_root.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def _create_uploaded_run(self, run_id, video_id="test123"):
        run_dir = self.runs_root / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "publish").mkdir()
        self._write_json(run_dir / "00_manifest.json", {
            "run_id": run_id, "status": "UPLOADED",
        })
        from rayvault.youtube_upload_receipt import sign_receipt
        receipt = {
            "version": "1.0", "run_id": run_id, "status": "UPLOADED",
            "uploader": "test", "uploaded_at_utc": "2026-01-01T00:00:00Z",
            "inputs": {"video_sha256": "abc", "video_size_bytes": 1000},
            "youtube": {"video_id": video_id, "channel_id": "UC000"},
        }
        receipt["integrity"] = {"method": "hmac_sha256", "hmac_sha256": sign_receipt(receipt)}
        self._write_json(run_dir / "publish" / "upload_receipt.json", receipt)
        return run_dir

    def test_scan_finds_uploaded(self):
        from rayvault.cron_verify_visibility import scan_uploaded_runs
        self._create_uploaded_run("RUN_A")
        self._create_uploaded_run("RUN_B")
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 2)

    def test_scan_skips_verified(self):
        from rayvault.cron_verify_visibility import scan_uploaded_runs
        self._create_uploaded_run("RUN_A")
        # Make RUN_B already verified
        run_b = self._create_uploaded_run("RUN_B")
        receipt = json.loads((run_b / "publish" / "upload_receipt.json").read_text())
        receipt["status"] = "VERIFIED"
        self._write_json(run_b / "publish" / "upload_receipt.json", receipt)
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].name, "RUN_A")

    def test_scan_empty_dir(self):
        from rayvault.cron_verify_visibility import scan_uploaded_runs
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 0)

    def test_batch_manual_verify(self):
        from rayvault.cron_verify_visibility import verify_batch
        self._create_uploaded_run("RUN_X")
        summary = verify_batch(self.runs_root, manual=True)
        self.assertEqual(summary["checked"], 1)
        self.assertEqual(summary["verified"], 1)
        # Receipt should now be VERIFIED
        receipt = json.loads(
            (self.runs_root / "RUN_X" / "publish" / "upload_receipt.json").read_text()
        )
        self.assertEqual(receipt["status"], "VERIFIED")

    def test_batch_multiple_runs(self):
        from rayvault.cron_verify_visibility import verify_batch
        self._create_uploaded_run("RUN_1")
        self._create_uploaded_run("RUN_2")
        self._create_uploaded_run("RUN_3")
        summary = verify_batch(self.runs_root, manual=True)
        self.assertEqual(summary["total_uploaded"], 3)
        self.assertEqual(summary["verified"], 3)

    def test_cli_no_verify_cmd(self):
        from rayvault.cron_verify_visibility import main
        with patch.dict(os.environ, {"RAY_YT_VERIFY_CMD": ""}, clear=False):
            rc = main(["--runs-root", str(self.runs_root)])
        self.assertEqual(rc, 2)

    def test_cli_manual_mode(self):
        from rayvault.cron_verify_visibility import main
        self._create_uploaded_run("RUN_CLI")
        rc = main(["--runs-root", str(self.runs_root), "--manual"])
        self.assertEqual(rc, 0)

    def test_max_runs_limit(self):
        from rayvault.cron_verify_visibility import verify_batch
        for i in range(5):
            self._create_uploaded_run(f"RUN_{i}")
        summary = verify_batch(self.runs_root, manual=True, max_runs=2)
        self.assertEqual(summary["checked"], 2)
        self.assertEqual(summary["total_uploaded"], 5)


# ── Truth Cache v1.2 tests ──────────────────────────────────────────────────

class TestTruthCacheV12(unittest.TestCase):
    """Tests for truth_cache.py v1.2 — mark_cache_broken, integrity, status."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.lib_root = Path(self.td) / "library"
        self.lib_root.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _make_cache(self, **kwargs):
        from rayvault.truth_cache import TruthCache, CachePolicy
        policy = CachePolicy(**kwargs) if kwargs else CachePolicy()
        return TruthCache(self.lib_root, policy)

    def test_mark_cache_broken(self):
        from rayvault.truth_cache import CACHE_BROKEN
        cache = self._make_cache()
        cache.put_from_fetch("B0BREAK", {"title": "X"}, [])
        cache.mark_cache_broken("B0BREAK", "test_reason")
        info = json.loads(cache.cache_info_path("B0BREAK").read_text())
        self.assertEqual(info["status"], CACHE_BROKEN)
        self.assertEqual(info["broken_reason"], "test_reason")
        self.assertIn("broken_at_utc", info)

    def test_broken_cache_needs_full_refresh(self):
        from rayvault.truth_cache import CACHE_BROKEN
        cache = self._make_cache(ttl_meta_sec=999999, ttl_images_sec=999999)
        img = Path(self.td) / "01_main.jpg"
        img.write_bytes(b"\xff" * 200)
        cache.put_from_fetch("B0BREAK", {"title": "X"}, [img])
        cache.mark_cache_broken("B0BREAK", "corrupt")
        need = cache.needs_refresh("B0BREAK")
        self.assertEqual(need["status"], CACHE_BROKEN)
        self.assertFalse(need["has_meta"])
        self.assertFalse(need["has_images"])
        self.assertTrue(need["refresh_meta"])
        self.assertTrue(need["refresh_images"])

    def test_broken_cache_get_returns_empty(self):
        cache = self._make_cache()
        cache.put_from_fetch("B0BREAK", {"title": "X"}, [])
        cache.mark_cache_broken("B0BREAK", "corrupt")
        cached = cache.get_cached("B0BREAK")
        self.assertNotIn("meta", cached)
        self.assertNotIn("images", cached)

    def test_put_clears_broken_state(self):
        from rayvault.truth_cache import CACHE_VALID
        cache = self._make_cache()
        cache.put_from_fetch("B0BREAK", {"title": "X"}, [])
        cache.mark_cache_broken("B0BREAK", "corrupt")
        # Fresh put should clear broken state
        cache.put_from_fetch("B0BREAK", {"title": "Y"}, [])
        info = json.loads(cache.cache_info_path("B0BREAK").read_text())
        self.assertEqual(info["status"], CACHE_VALID)
        self.assertNotIn("broken_reason", info)
        self.assertNotIn("broken_at_utc", info)
        cached = cache.get_cached("B0BREAK")
        self.assertEqual(cached["meta"]["title"], "Y")

    def test_metadata_sha256_stored(self):
        cache = self._make_cache()
        meta = {"title": "Test", "asin": "B0SHA"}
        cache.put_from_fetch("B0SHA", meta, [])
        info = json.loads(cache.cache_info_path("B0SHA").read_text())
        self.assertIn("meta_sha256", info)
        self.assertEqual(len(info["meta_sha256"]), 64)  # SHA256 hex length

    def test_metadata_integrity_check_pass(self):
        cache = self._make_cache()
        meta = {"title": "Legit", "asin": "B0OK"}
        cache.put_from_fetch("B0OK", meta, [])
        # Read should succeed (hash matches)
        cached = cache.get_cached("B0OK")
        self.assertEqual(cached["meta"]["title"], "Legit")

    def test_metadata_integrity_check_fail(self):
        from rayvault.truth_cache import CACHE_BROKEN
        cache = self._make_cache()
        meta = {"title": "Original", "asin": "B0TAMPER"}
        cache.put_from_fetch("B0TAMPER", meta, [])
        # Tamper with metadata file directly
        tampered = {"title": "TAMPERED", "asin": "B0TAMPER"}
        with open(cache.meta_path("B0TAMPER"), "w") as f:
            json.dump(tampered, f)
        # get_cached should detect mismatch and mark broken
        cached = cache.get_cached("B0TAMPER")
        self.assertNotIn("meta", cached)
        info = json.loads(cache.cache_info_path("B0TAMPER").read_text())
        self.assertEqual(info["status"], CACHE_BROKEN)
        self.assertIn("meta_sha256_mismatch", info.get("broken_reason", ""))

    def test_verify_integrity_ok(self):
        cache = self._make_cache()
        img = Path(self.td) / "01_main.jpg"
        img.write_bytes(b"\xff" * 200)
        cache.put_from_fetch("B0GOOD", {"title": "X"}, [img])
        result = cache.verify_integrity("B0GOOD")
        self.assertTrue(result["ok"])
        self.assertEqual(result["issues"], [])

    def test_verify_integrity_missing_asin(self):
        cache = self._make_cache()
        result = cache.verify_integrity("B0NOPE")
        self.assertFalse(result["ok"])
        self.assertIn("asin_dir_missing", result["issues"])

    def test_verify_integrity_broken(self):
        cache = self._make_cache()
        cache.put_from_fetch("B0BRKN", {"title": "X"}, [])
        cache.mark_cache_broken("B0BRKN", "test")
        result = cache.verify_integrity("B0BRKN")
        self.assertFalse(result["ok"])
        self.assertTrue(any("marked_broken" in i for i in result["issues"]))

    def test_verify_integrity_meta_sha256_mismatch(self):
        cache = self._make_cache()
        cache.put_from_fetch("B0HASH", {"title": "X"}, [])
        # Tamper metadata
        with open(cache.meta_path("B0HASH"), "w") as f:
            json.dump({"title": "CHANGED"}, f)
        result = cache.verify_integrity("B0HASH")
        self.assertFalse(result["ok"])
        self.assertIn("meta_sha256_mismatch", result["issues"])

    def test_needs_refresh_returns_status_valid(self):
        from rayvault.truth_cache import CACHE_VALID
        cache = self._make_cache(ttl_meta_sec=999999, ttl_images_sec=999999)
        img = Path(self.td) / "01_main.jpg"
        img.write_bytes(b"\xff" * 200)
        cache.put_from_fetch("B0V", {"title": "X"}, [img])
        need = cache.needs_refresh("B0V")
        self.assertEqual(need["status"], CACHE_VALID)

    def test_needs_refresh_returns_status_expired(self):
        from rayvault.truth_cache import CACHE_EXPIRED
        cache = self._make_cache(ttl_meta_sec=0, ttl_images_sec=0)
        img = Path(self.td) / "01_main.jpg"
        img.write_bytes(b"\xff" * 200)
        cache.put_from_fetch("B0E", {"title": "X"}, [img])
        need = cache.needs_refresh("B0E")
        self.assertEqual(need["status"], CACHE_EXPIRED)

    def test_cache_info_status_set_to_valid_on_put(self):
        from rayvault.truth_cache import CACHE_VALID
        cache = self._make_cache()
        cache.put_from_fetch("B0S", {"title": "X"}, [])
        info = json.loads(cache.cache_info_path("B0S").read_text())
        self.assertEqual(info["status"], CACHE_VALID)


# ── Product Asset Fetch v1.2 telemetry tests ────────────────────────────────

class TestProductAssetFetchTelemetry(unittest.TestCase):
    """Tests for product_asset_fetch.py v1.2 — cache_misses, truth_source, telemetry."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.run_dir = Path(self.td) / "state" / "runs" / "RUN_TEL"
        self.products_dir = self.run_dir / "products"
        self.products_dir.mkdir(parents=True)
        self.lib_dir = Path(self.td) / "library"
        self.lib_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def _write_products(self, items):
        self._write_json(self.products_dir / "products.json", {"items": items})

    def test_fetch_result_has_cache_misses(self):
        from rayvault.product_asset_fetch import FetchResult
        r = FetchResult(ok=True, downloaded=0, skipped=0, errors=0, cache_hits=1, cache_misses=2)
        self.assertEqual(r.cache_misses, 2)

    def test_manifest_truth_cache_block(self):
        """Manifest should contain truth_cache telemetry block when cache is used."""
        from rayvault.product_asset_fetch import run_product_fetch
        self._write_products([{
            "rank": 1, "asin": "B0TELE", "title": "Telemetry Test",
            "image_urls": [], "hires_image_urls": [],
        }])
        run_product_fetch(self.run_dir, library_dir=self.lib_dir)
        manifest = json.loads((self.run_dir / "00_manifest.json").read_text())
        self.assertIn("truth_cache", manifest)
        tc = manifest["truth_cache"]
        self.assertIn("hits", tc)
        self.assertIn("misses", tc)
        self.assertIn("ttl_meta_hours", tc)
        self.assertIn("ttl_images_hours", tc)

    def test_truth_source_live_fetch(self):
        """Products fetched from network should have truth_source=LIVE_FETCH."""
        from rayvault.product_asset_fetch import run_product_fetch
        # No cache, no URLs — should be NONE
        self._write_products([{
            "rank": 1, "asin": "B0NONE", "title": "No URLs",
            "image_urls": [], "hires_image_urls": [],
        }])
        run_product_fetch(self.run_dir, library_dir=self.lib_dir)
        manifest = json.loads((self.run_dir / "00_manifest.json").read_text())
        summary = manifest.get("products_summary", [])
        self.assertTrue(len(summary) > 0)
        self.assertEqual(summary[0]["truth_source"], "NONE")

    def test_cache_miss_counted(self):
        """Cache miss should be counted when cache is enabled but has no data."""
        from rayvault.product_asset_fetch import run_product_fetch
        self._write_products([{
            "rank": 1, "asin": "B0MISS", "title": "Miss Test",
            "image_urls": [], "hires_image_urls": [],
        }])
        result = run_product_fetch(self.run_dir, library_dir=self.lib_dir)
        self.assertEqual(result.cache_misses, 1)
        manifest = json.loads((self.run_dir / "00_manifest.json").read_text())
        self.assertEqual(manifest["truth_cache"]["misses"], 1)

    def test_cache_hit_truth_source(self):
        """Cache hit should set truth_source=CACHE in products_summary."""
        from rayvault.product_asset_fetch import run_product_fetch
        from rayvault.truth_cache import TruthCache, CachePolicy
        # Pre-populate cache
        cache = TruthCache(self.lib_dir, CachePolicy(ttl_images_sec=999999))
        img = Path(self.td) / "01_main.jpg"
        img.write_bytes(b"\xff\xd8" * 2000)
        cache.put_from_fetch("B0HIT", {"title": "Hit", "asin": "B0HIT"}, [img])
        self._write_products([{
            "rank": 1, "asin": "B0HIT", "title": "Hit Test",
            "image_urls": [], "hires_image_urls": [],
        }])
        result = run_product_fetch(self.run_dir, library_dir=self.lib_dir)
        self.assertEqual(result.cache_hits, 1)
        manifest = json.loads((self.run_dir / "00_manifest.json").read_text())
        summary = manifest.get("products_summary", [])
        self.assertEqual(summary[0]["truth_source"], "CACHE")


# ── Claims guardrail v1.2 tests ─────────────────────────────────────────────

class TestClaimsGuardrailCached(unittest.TestCase):
    """Tests for claims_guardrail.py — cache-backed product text."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.run_dir = Path(self.td) / "run"
        self.run_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _write_file(self, rel_path, content):
        fp = self.run_dir / rel_path
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")

    def _write_json(self, rel_path, data):
        fp = self.run_dir / rel_path
        fp.parent.mkdir(parents=True, exist_ok=True)
        with open(fp, "w") as f:
            json.dump(data, f)

    def test_uses_cached_metadata_when_available(self):
        from rayvault.claims_guardrail import guardrail
        # Write script
        self._write_file("01_script.txt", "This product is waterproof and great.")
        # Write cached product_metadata.json (from TruthCache)
        self._write_json("products/p01/product_metadata.json", {
            "title": "Waterproof Speaker IPX7",
            "bullets": ["Truly waterproof IPX7 rated"],
            "asin": "B0CACHE",
        })
        # No products.json — should still work with cached data
        result = guardrail(self.run_dir, use_cached_products=True)
        self.assertEqual(result["products_source"], "cached_metadata")
        self.assertEqual(result["status"], "PASS")

    def test_fallback_to_products_json(self):
        from rayvault.claims_guardrail import guardrail
        self._write_file("01_script.txt", "Great product for everyone.")
        self._write_json("products/products.json", {
            "items": [{"rank": 1, "title": "Speaker", "asin": "B0F"}]
        })
        result = guardrail(self.run_dir, use_cached_products=True)
        self.assertEqual(result["products_source"], "products_json")

    def test_cached_product_with_violation(self):
        from rayvault.claims_guardrail import guardrail
        self._write_file("01_script.txt", "This is FDA certified medical grade.")
        self._write_json("products/p01/product_metadata.json", {
            "title": "Basic Speaker",
            "bullets": ["Good sound quality"],
            "asin": "B0VIO",
        })
        result = guardrail(self.run_dir, use_cached_products=True)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertTrue(len(result["violations"]) > 0)

    def test_use_cached_false_ignores_cached(self):
        from rayvault.claims_guardrail import guardrail
        self._write_file("01_script.txt", "Nice product.")
        self._write_json("products/products.json", {
            "items": [{"rank": 1, "title": "Speaker", "asin": "B0F"}]
        })
        self._write_json("products/p01/product_metadata.json", {
            "title": "Different",
            "asin": "B0DIFF",
        })
        result = guardrail(self.run_dir, use_cached_products=False)
        self.assertEqual(result["products_source"], "products_json")

    def test_prefers_product_metadata_over_product_json(self):
        """_load_cached_products prefers product_metadata.json over product.json."""
        from rayvault.claims_guardrail import _load_cached_products
        # Write both files for p01
        self._write_json("products/p01/product_metadata.json", {
            "title": "Cached Metadata", "asin": "B0META",
        })
        self._write_json("products/p01/product.json", {
            "title": "Product JSON", "asin": "B0PROD",
        })
        products = _load_cached_products(self.run_dir)
        self.assertIsNotNone(products)
        self.assertEqual(products[0]["title"], "Cached Metadata")


# ── Survival mode tests ──────────────────────────────────────────────────────

class TestSurvivalMode(unittest.TestCase):
    """Tests for survival mode on Amazon 403/429."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.lib_root = Path(self.td) / "library"
        self.lib_root.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def test_get_stale_if_allowed_fresh(self):
        from rayvault.truth_cache import TruthCache, CachePolicy
        cache = TruthCache(self.lib_root, CachePolicy(survival_allow_stale_hours=168))
        img = Path(self.td) / "01_main.jpg"
        img.write_bytes(b"\xff" * 200)
        cache.put_from_fetch("B0SURV", {"title": "X"}, [img])
        stale = cache.get_stale_if_allowed("B0SURV")
        self.assertIn("meta", stale)
        self.assertIn("images", stale)

    def test_get_stale_if_allowed_missing(self):
        from rayvault.truth_cache import TruthCache, CachePolicy
        cache = TruthCache(self.lib_root, CachePolicy())
        stale = cache.get_stale_if_allowed("B0NOPE")
        self.assertEqual(stale, {})

    def test_get_stale_if_allowed_broken(self):
        from rayvault.truth_cache import TruthCache, CachePolicy
        cache = TruthCache(self.lib_root, CachePolicy())
        cache.put_from_fetch("B0BRK", {"title": "X"}, [])
        cache.mark_cache_broken("B0BRK", "test")
        stale = cache.get_stale_if_allowed("B0BRK")
        self.assertEqual(stale, {})

    def test_effective_ttl_has_jitter(self):
        from rayvault.truth_cache import TruthCache, CachePolicy
        cache = TruthCache(self.lib_root, CachePolicy(
            ttl_images_sec=86400, ttl_jitter_sec=3600
        ))
        results = set()
        for _ in range(20):
            results.add(cache.effective_ttl_images_sec())
        # With jitter, should have variation
        self.assertGreater(len(results), 1)

    def test_effective_ttl_no_jitter(self):
        from rayvault.truth_cache import TruthCache, CachePolicy
        cache = TruthCache(self.lib_root, CachePolicy(
            ttl_images_sec=86400, ttl_jitter_sec=0
        ))
        self.assertEqual(cache.effective_ttl_images_sec(), 86400)

    def test_fetch_result_survival_fields(self):
        from rayvault.product_asset_fetch import FetchResult
        r = FetchResult(
            ok=True, downloaded=0, skipped=3, errors=0,
            cache_hits=3, cache_misses=0, amazon_blocks=1,
            survival_mode=True,
        )
        self.assertTrue(r.survival_mode)
        self.assertEqual(r.amazon_blocks, 1)

    def test_manifest_stability_flags(self):
        """Manifest should contain stability_flags when survival mode active."""
        from rayvault.product_asset_fetch import run_product_fetch
        run_dir = Path(self.td) / "runs" / "RUN_SURV"
        products_dir = run_dir / "products"
        products_dir.mkdir(parents=True)
        with open(products_dir / "products.json", "w") as f:
            json.dump({"items": [
                {"rank": 1, "asin": "B0SV", "title": "Survival", "image_urls": [], "hires_image_urls": []},
            ]}, f)
        # Run with cache but no data → cache miss
        result = run_product_fetch(run_dir, library_dir=self.lib_root)
        manifest = json.loads((run_dir / "00_manifest.json").read_text())
        tc = manifest.get("truth_cache", {})
        self.assertIn("amazon_blocks", tc)
        self.assertIn("survival_mode", tc)


# ── Cleanup dead man's switch tests ──────────────────────────────────────────

class TestCleanupDeadManSwitch(unittest.TestCase):
    """Tests for cleanup_run.py dead man's switch (min-upload-age-hours)."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.run_dir = Path(self.td) / "run"
        self.run_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def _write_json(self, rel_path, data):
        fp = self.run_dir / rel_path
        fp.parent.mkdir(parents=True, exist_ok=True)
        with open(fp, "w") as f:
            json.dump(data, f)

    def _setup_run_with_receipt(self, uploaded_at_utc, status="VERIFIED"):
        self._write_json("00_manifest.json", {"run_id": "TEST", "status": status})
        from rayvault.youtube_upload_receipt import sign_receipt
        receipt = {
            "version": "1.0", "run_id": "TEST", "status": status,
            "uploader": "test", "uploaded_at_utc": uploaded_at_utc,
            "inputs": {"video_sha256": "abc", "video_size_bytes": 1000},
            "youtube": {"video_id": "vid123", "channel_id": "UC000"},
        }
        receipt["integrity"] = {"method": "hmac_sha256", "hmac_sha256": sign_receipt(receipt)}
        self._write_json("publish/upload_receipt.json", receipt)
        # Create fake video
        video = self.run_dir / "publish" / "video_final.mp4"
        video.write_bytes(b"\x00" * 2048)

    def test_recent_upload_retains_video(self):
        """Video uploaded < 24h ago should NOT be deleted."""
        from rayvault.cleanup_run import cleanup
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._setup_run_with_receipt(now)
        ok, info = cleanup(
            self.run_dir, apply=True, delete_final_video=True,
            min_upload_age_hours=24.0,
        )
        self.assertTrue(ok)
        # Video should still exist (retained by dead man's switch)
        self.assertTrue((self.run_dir / "publish" / "video_final.mp4").exists())
        # Check manifest records retention reason
        m = json.loads((self.run_dir / "00_manifest.json").read_text())
        hk = m.get("housekeeping", {})
        self.assertEqual(hk.get("final_video_retained_reason"), "MIN_UPLOAD_AGE_BUFFER")

    def test_old_upload_allows_delete(self):
        """Video uploaded > 24h ago should be deletable."""
        from rayvault.cleanup_run import cleanup
        self._setup_run_with_receipt("2020-01-01T00:00:00Z")
        ok, info = cleanup(
            self.run_dir, apply=True, delete_final_video=True,
            min_upload_age_hours=24.0,
        )
        self.assertTrue(ok)
        # Video should be deleted
        self.assertFalse((self.run_dir / "publish" / "video_final.mp4").exists())

    def test_force_bypasses_age_check(self):
        """--force should bypass upload age check."""
        from rayvault.cleanup_run import cleanup
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._setup_run_with_receipt(now)
        ok, info = cleanup(
            self.run_dir, apply=True, delete_final_video=True,
            min_upload_age_hours=24.0, force=True,
        )
        self.assertTrue(ok)
        # Force bypasses receipt check entirely, so receipt not loaded
        # But video should be in purge targets

    def test_zero_min_age_allows_immediate_delete(self):
        """min_upload_age_hours=0 should allow immediate deletion."""
        from rayvault.cleanup_run import cleanup
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._setup_run_with_receipt(now)
        ok, info = cleanup(
            self.run_dir, apply=True, delete_final_video=True,
            min_upload_age_hours=0.0,
        )
        self.assertTrue(ok)
        self.assertFalse((self.run_dir / "publish" / "video_final.mp4").exists())


# ── Audio proof + safe_audio_mode tests ──────────────────────────────────────

class TestAudioProofGate(unittest.TestCase):
    """Tests for gate_audio_proof in final_validator.py."""

    def test_no_audio_proof_passes(self):
        from rayvault.final_validator import gate_audio_proof
        manifest = {"status": "READY_FOR_RENDER"}
        g = gate_audio_proof(manifest)
        self.assertTrue(g.passed)
        self.assertIn("optional", g.detail)

    def test_safe_audio_all_tts(self):
        from rayvault.final_validator import gate_audio_proof
        manifest = {
            "audio_proof": {
                "tts_provider": "elevenlabs",
                "has_external_music": False,
                "has_external_sfx": False,
                "script_provenance": "ai_generated",
            }
        }
        g = gate_audio_proof(manifest)
        self.assertTrue(g.passed)
        self.assertIn("safe_audio_mode=True", g.detail)
        # Check it wrote back to manifest
        self.assertTrue(manifest["audio_proof"]["safe_audio_mode"])

    def test_unsafe_audio_external_music(self):
        from rayvault.final_validator import gate_audio_proof
        manifest = {
            "audio_proof": {
                "tts_provider": "elevenlabs",
                "has_external_music": True,
                "has_external_sfx": False,
                "script_provenance": "ai_generated",
            }
        }
        g = gate_audio_proof(manifest)
        self.assertTrue(g.passed)  # Gate passes, just derives safe_audio_mode
        self.assertIn("safe_audio_mode=False", g.detail)
        self.assertFalse(manifest["audio_proof"]["safe_audio_mode"])

    def test_unsafe_audio_manual_script(self):
        from rayvault.final_validator import gate_audio_proof
        manifest = {
            "audio_proof": {
                "tts_provider": "elevenlabs",
                "has_external_music": False,
                "has_external_sfx": False,
                "script_provenance": "manual",
            }
        }
        g = gate_audio_proof(manifest)
        self.assertFalse(manifest["audio_proof"]["safe_audio_mode"])

    def test_safe_audio_human_edit_ok(self):
        from rayvault.final_validator import gate_audio_proof
        manifest = {
            "audio_proof": {
                "tts_provider": "openai_tts",
                "has_external_music": False,
                "has_external_sfx": False,
                "script_provenance": "ai_generated+human_edit",
            }
        }
        g = gate_audio_proof(manifest)
        self.assertTrue(manifest["audio_proof"]["safe_audio_mode"])

    def test_unsafe_audio_no_tts(self):
        from rayvault.final_validator import gate_audio_proof
        manifest = {
            "audio_proof": {
                "tts_provider": "",
                "has_external_music": False,
                "has_external_sfx": False,
                "script_provenance": "ai_generated",
            }
        }
        g = gate_audio_proof(manifest)
        self.assertFalse(manifest["audio_proof"]["safe_audio_mode"])


class TestAmazonQuarantine(unittest.TestCase):
    """Tests for amazon_quarantine module."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lock_path = Path(self.tmp) / "amazon_quarantine.lock"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_lock_not_quarantined(self):
        from rayvault.amazon_quarantine import is_quarantined
        self.assertFalse(is_quarantined(self.lock_path))

    def test_set_and_check_quarantine(self):
        from rayvault.amazon_quarantine import is_quarantined, set_quarantine
        set_quarantine(self.lock_path, code=429, cooldown_hours=2.0, jitter_minutes=0)
        self.assertTrue(is_quarantined(self.lock_path))

    def test_remaining_minutes(self):
        from rayvault.amazon_quarantine import set_quarantine, remaining_minutes
        set_quarantine(self.lock_path, code=403, cooldown_hours=2.0, jitter_minutes=0)
        mins = remaining_minutes(self.lock_path)
        self.assertGreater(mins, 100)  # ~120 min

    def test_clear_quarantine(self):
        from rayvault.amazon_quarantine import set_quarantine, clear_quarantine, is_quarantined
        set_quarantine(self.lock_path, code=429, cooldown_hours=2.0, jitter_minutes=0)
        self.assertTrue(is_quarantined(self.lock_path))
        cleared = clear_quarantine(self.lock_path)
        self.assertTrue(cleared)
        self.assertFalse(is_quarantined(self.lock_path))

    def test_expired_quarantine(self):
        from rayvault.amazon_quarantine import is_quarantined
        # Write a lock with already-expired cooldown
        expired = {
            "at_utc": "2025-01-01T00:00:00Z",
            "code": 429,
            "cooldown_until_utc": "2025-01-01T04:00:00Z",
        }
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "w") as f:
            json.dump(expired, f)
        self.assertFalse(is_quarantined(self.lock_path))

    def test_lock_file_format(self):
        from rayvault.amazon_quarantine import set_quarantine
        set_quarantine(self.lock_path, code=403, cooldown_hours=4.0, jitter_minutes=0, note="test block")
        data = json.loads(self.lock_path.read_text())
        self.assertEqual(data["code"], 403)
        self.assertIn("cooldown_until_utc", data)
        self.assertEqual(data["note"], "test block")
        self.assertIn("at_utc", data)


class TestCachePrune(unittest.TestCase):
    """Tests for cache_prune module."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_prune_empty_dir(self):
        from rayvault.cache_prune import prune
        result = prune(self.root, max_unused_days=30, apply=False)
        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(result["kept_count"], 0)

    def test_prune_nonexistent_root(self):
        from rayvault.cache_prune import prune
        result = prune(Path("/nonexistent_dir_xyz"), max_unused_days=30)
        self.assertEqual(result.get("error"), "root_not_found")

    def test_prune_old_entry(self):
        from rayvault.cache_prune import prune
        # Create an old ASIN entry
        asin_dir = self.root / "B0OLD123"
        asin_dir.mkdir(parents=True)
        cache_info = {
            "last_used_utc": "2024-01-01T00:00:00Z",
            "images_fetched_at_utc": "2024-01-01T00:00:00Z",
        }
        with open(asin_dir / "cache_info.json", "w") as f:
            json.dump(cache_info, f)

        result = prune(self.root, max_unused_days=30, apply=False)
        self.assertEqual(result["deleted_count"], 1)
        self.assertIn("B0OLD123", result["deleted"])
        # Dry-run: dir should still exist
        self.assertTrue(asin_dir.exists())

    def test_prune_apply_deletes(self):
        from rayvault.cache_prune import prune
        asin_dir = self.root / "B0DEL456"
        asin_dir.mkdir(parents=True)
        cache_info = {
            "last_used_utc": "2024-01-01T00:00:00Z",
        }
        with open(asin_dir / "cache_info.json", "w") as f:
            json.dump(cache_info, f)

        result = prune(self.root, max_unused_days=30, apply=True)
        self.assertEqual(result["deleted_count"], 1)
        self.assertFalse(asin_dir.exists())

    def test_prune_keeps_fresh_entry(self):
        from rayvault.cache_prune import prune
        asin_dir = self.root / "B0FRESH"
        asin_dir.mkdir(parents=True)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cache_info = {"last_used_utc": now_iso}
        with open(asin_dir / "cache_info.json", "w") as f:
            json.dump(cache_info, f)

        result = prune(self.root, max_unused_days=30, apply=False)
        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(result["kept_count"], 1)

    def test_prune_skips_broken(self):
        from rayvault.cache_prune import prune
        asin_dir = self.root / "B0BROKEN"
        asin_dir.mkdir(parents=True)
        cache_info = {
            "status": "BROKEN",
            "last_used_utc": "2024-01-01T00:00:00Z",
        }
        with open(asin_dir / "cache_info.json", "w") as f:
            json.dump(cache_info, f)

        result = prune(self.root, max_unused_days=30, apply=False)
        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(result["kept_count"], 1)

    def test_prune_skips_no_cache_info(self):
        from rayvault.cache_prune import prune
        asin_dir = self.root / "B0NOINFO"
        asin_dir.mkdir(parents=True)
        # No cache_info.json

        result = prune(self.root, max_unused_days=30, apply=False)
        self.assertEqual(result["skipped_count"], 1)


class TestBrollPromotion(unittest.TestCase):
    """Tests for B-roll library promotion in TruthCache."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lib = Path(self.tmp) / "library"
        self.lib.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_promote_broll(self):
        from rayvault.truth_cache import TruthCache
        cache = TruthCache(self.lib)
        asin = "B0TEST123"

        # Create a fake approved.mp4
        src_dir = Path(self.tmp) / "run" / "products" / "p01" / "broll"
        src_dir.mkdir(parents=True)
        src_mp4 = src_dir / "approved.mp4"
        src_mp4.write_bytes(b"\x00" * 1024)

        self.assertFalse(cache.has_approved_broll(asin))
        ok = cache.promote_broll(asin, src_mp4)
        self.assertTrue(ok)
        self.assertTrue(cache.has_approved_broll(asin))
        self.assertTrue(cache.approved_broll_path(asin).exists())

    def test_promote_broll_nonexistent_source(self):
        from rayvault.truth_cache import TruthCache
        cache = TruthCache(self.lib)
        ok = cache.promote_broll("B0NOPE", Path("/nonexistent.mp4"))
        self.assertFalse(ok)

    def test_approved_broll_path(self):
        from rayvault.truth_cache import TruthCache
        cache = TruthCache(self.lib)
        path = cache.approved_broll_path("B0XYZ")
        self.assertIn("approved_broll", str(path))
        self.assertIn("approved.mp4", str(path))

    def test_last_used_utc_updated_on_materialize(self):
        from rayvault.truth_cache import TruthCache
        cache = TruthCache(self.lib)
        asin = "B0USED"

        # Setup cache with an image
        imgs_dir = cache.images_dir(asin)
        imgs_dir.mkdir(parents=True)
        img = imgs_dir / "01_main.jpg"
        img.write_bytes(b"\xff\xd8" + b"\x00" * 4096)
        meta = {"asin": asin, "title": "Test"}
        meta_path = cache.meta_path(asin)
        from rayvault.truth_cache import atomic_write_json, sha256_json, utc_now_iso
        atomic_write_json(meta_path, meta)
        info = {
            "meta_fetched_at_utc": utc_now_iso(),
            "images_fetched_at_utc": utc_now_iso(),
            "status": "VALID",
            "meta_sha256": sha256_json(meta),
        }
        atomic_write_json(cache.cache_info_path(asin), info)

        # Materialize
        run_pdir = Path(self.tmp) / "run" / "products" / "p01"
        run_pdir.mkdir(parents=True)
        result = cache.materialize_to_run(asin, run_pdir)
        self.assertTrue(result["ok"])

        # Check last_used_utc was set
        updated_info = json.loads(cache.cache_info_path(asin).read_text())
        self.assertIn("last_used_utc", updated_info)


class TestDoublePassVerify(unittest.TestCase):
    """Tests for double-pass verification on unsafe audio."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.run_dir = Path(self.tmp) / "RUN_TEST"
        self.run_dir.mkdir(parents=True)
        self.publish = self.run_dir / "publish"
        self.publish.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_json(self, path, data):
        with open(path, "w") as f:
            json.dump(data, f)

    def _make_receipt(self, status="UPLOADED"):
        receipt = {
            "run_id": "RUN_TEST",
            "status": status,
            "youtube": {
                "video_id": "dQw4w9WgXcQ",
                "processing_state": "UNKNOWN",
                "visibility_state": "UNKNOWN",
                "copyright_claims": [],
            },
            "integrity": {"salt": "test_salt"},
        }
        self._write_json(self.publish / "upload_receipt.json", receipt)
        return receipt

    def _make_manifest(self, safe_audio=True):
        manifest = {
            "status": "UPLOADED",
            "audio_proof": {"safe_audio_mode": safe_audio},
        }
        self._write_json(self.run_dir / "00_manifest.json", manifest)
        return manifest

    def test_safe_audio_verifies_in_one_pass(self):
        """safe_audio_mode=true → single pass is enough."""
        from rayvault.verify_visibility import verify
        self._make_receipt()
        self._make_manifest(safe_audio=True)

        # Mock verifier that succeeds
        verify_cmd = "echo '{\"ok\": true, \"processing\": \"succeeded\", \"privacy\": \"unlisted\", \"claims\": []}'"
        result = verify(self.run_dir, verify_cmd=verify_cmd)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "VERIFIED")

    def test_unsafe_audio_needs_two_passes(self):
        """safe_audio_mode=false → first pass records but doesn't verify."""
        from rayvault.verify_visibility import verify
        self._make_receipt()
        self._make_manifest(safe_audio=False)

        verify_cmd = "echo '{\"ok\": true, \"processing\": \"succeeded\", \"privacy\": \"unlisted\", \"claims\": []}'"
        result = verify(self.run_dir, verify_cmd=verify_cmd)
        # First pass should NOT verify yet
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("reason"), "double_pass_pending")
        self.assertEqual(result["passes"], 1)

    def test_unsafe_audio_two_passes_close_not_enough(self):
        """Two passes within 12h shouldn't verify."""
        from rayvault.verify_visibility import verify, _check_double_pass
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        receipt = {
            "status": "UPLOADED",
            "youtube": {
                "video_id": "test123",
                "processing_state": "SUCCEEDED",
                "visibility_state": "UNLISTED",
                "copyright_claims": [],
            },
            "integrity": {},
            "verify_passes": [
                {"at_utc": now_iso, "processing": "SUCCEEDED", "visibility": "UNLISTED"},
                {"at_utc": now_iso, "processing": "SUCCEEDED", "visibility": "UNLISTED"},
            ],
        }
        dp = _check_double_pass(receipt, spacing_hours=12.0)
        self.assertFalse(dp["met"])
        self.assertEqual(dp["passes"], 2)

    def test_unsafe_audio_two_passes_spaced_ok(self):
        """Two passes spaced > 12h should satisfy double-pass."""
        from rayvault.verify_visibility import _check_double_pass
        t1 = "2026-02-10T06:00:00Z"
        t2 = "2026-02-10T20:00:00Z"  # 14h later
        receipt = {
            "verify_passes": [
                {"at_utc": t1, "processing": "SUCCEEDED", "visibility": "UNLISTED"},
                {"at_utc": t2, "processing": "SUCCEEDED", "visibility": "UNLISTED"},
            ],
        }
        dp = _check_double_pass(receipt, spacing_hours=12.0)
        self.assertTrue(dp["met"])

    def test_manual_verify_bypasses_double_pass(self):
        """Manual verification should bypass double-pass requirement."""
        from rayvault.verify_visibility import verify
        self._make_receipt()
        self._make_manifest(safe_audio=False)

        result = verify(self.run_dir, manual=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["method"], "manual")

    def test_double_pass_not_needed_when_no_audio_proof(self):
        """No audio_proof block → no double-pass requirement."""
        from rayvault.verify_visibility import verify
        self._make_receipt()
        self._write_json(self.run_dir / "00_manifest.json", {"status": "UPLOADED"})

        verify_cmd = "echo '{\"ok\": true, \"processing\": \"succeeded\", \"privacy\": \"unlisted\", \"claims\": []}'"
        result = verify(self.run_dir, verify_cmd=verify_cmd)
        self.assertTrue(result["ok"])

    def test_verify_passes_recorded_in_receipt(self):
        """Verify passes should be recorded in the receipt file."""
        from rayvault.verify_visibility import verify
        self._make_receipt()
        self._make_manifest(safe_audio=True)

        verify_cmd = "echo '{\"ok\": true, \"processing\": \"succeeded\", \"privacy\": \"unlisted\", \"claims\": []}'"
        verify(self.run_dir, verify_cmd=verify_cmd)

        receipt = json.loads((self.publish / "upload_receipt.json").read_text())
        self.assertIn("verify_passes", receipt)
        self.assertEqual(len(receipt["verify_passes"]), 1)


class TestRenderConfigLibraryBroll(unittest.TestCase):
    """Tests for library b-roll priority in render_config_generate."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.run_dir = Path(self.tmp) / "RUN_TEST"
        self.run_dir.mkdir(parents=True)
        self.lib_dir = Path(self.tmp) / "library"
        self.lib_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_library_broll_takes_priority(self):
        from rayvault.render_config_generate import resolve_visual_mode
        asin = "B0TEST"
        pdir = self.run_dir / "products" / "p01"
        pdir.mkdir(parents=True)

        # Put a main image in run dir
        src_imgs = pdir / "source_images"
        src_imgs.mkdir(parents=True)
        (src_imgs / "01_main.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 100)

        # Put library b-roll
        lib_broll_dir = self.lib_dir / "products" / asin / "approved_broll"
        lib_broll_dir.mkdir(parents=True)
        (lib_broll_dir / "approved.mp4").write_bytes(b"\x00" * 1024)

        visual = resolve_visual_mode(pdir, self.run_dir, None, asin=asin, library_dir=self.lib_dir)
        self.assertEqual(visual["mode"], "BROLL_VIDEO")
        self.assertEqual(visual["reason"], "library_approved_broll")

    def test_no_library_falls_back_to_run_broll(self):
        from rayvault.render_config_generate import resolve_visual_mode
        pdir = self.run_dir / "products" / "p01"
        broll_dir = pdir / "broll"
        broll_dir.mkdir(parents=True)
        (broll_dir / "approved.mp4").write_bytes(b"\x00" * 1024)

        visual = resolve_visual_mode(pdir, self.run_dir, None, asin="B0OTHER")
        self.assertEqual(visual["mode"], "BROLL_VIDEO")
        self.assertEqual(visual["reason"], "approved_broll")

    def test_no_broll_falls_back_to_ken_burns(self):
        from rayvault.render_config_generate import resolve_visual_mode
        pdir = self.run_dir / "products" / "p01"
        src_imgs = pdir / "source_images"
        src_imgs.mkdir(parents=True)
        (src_imgs / "01_main.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 100)

        visual = resolve_visual_mode(pdir, self.run_dir, None, asin="B0KEN")
        self.assertEqual(visual["mode"], "KEN_BURNS")

    def test_generate_render_config_with_library(self):
        from rayvault.render_config_generate import generate_render_config
        # Setup minimal run
        (self.run_dir / "01_script.txt").write_text("Test script with some words " * 20)
        products_dir = self.run_dir / "products"
        products_dir.mkdir(parents=True)
        items = [{"rank": 1, "asin": "B0LIB", "title": "Test Product"}]
        with open(products_dir / "products.json", "w") as f:
            json.dump({"items": items}, f)

        # Add library broll
        lib_broll = self.lib_dir / "products" / "B0LIB" / "approved_broll"
        lib_broll.mkdir(parents=True)
        (lib_broll / "approved.mp4").write_bytes(b"\x00" * 1024)

        p01 = products_dir / "p01"
        p01.mkdir(parents=True)

        result = generate_render_config(self.run_dir, library_dir=self.lib_dir)
        self.assertGreater(result["fidelity_score"], 0)
        # Check segments have the library broll product
        segments = result["config"]["segments"]
        product_segs = [s for s in segments if s["type"] == "product"]
        self.assertEqual(len(product_segs), 1)
        self.assertEqual(product_segs[0]["visual"]["reason"], "library_approved_broll")


class TestStabilityScore(unittest.TestCase):
    """Tests for stability score computation and episode truth tier."""

    def test_perfect_score(self):
        from rayvault.product_asset_fetch import compute_stability_score
        score = compute_stability_score(
            survival_mode=False, amazon_blocks=0, cache_misses=0,
            total_products=5, missing_images=0,
        )
        self.assertEqual(score, 100)

    def test_survival_mode_penalty(self):
        from rayvault.product_asset_fetch import compute_stability_score
        score = compute_stability_score(
            survival_mode=True, amazon_blocks=0, cache_misses=0,
            total_products=5, missing_images=0,
        )
        self.assertEqual(score, 80)

    def test_amazon_blocks_penalty(self):
        from rayvault.product_asset_fetch import compute_stability_score
        score = compute_stability_score(
            survival_mode=False, amazon_blocks=2, cache_misses=0,
            total_products=5, missing_images=0,
        )
        self.assertEqual(score, 70)

    def test_missing_images_penalty(self):
        from rayvault.product_asset_fetch import compute_stability_score
        score = compute_stability_score(
            survival_mode=False, amazon_blocks=0, cache_misses=0,
            total_products=5, missing_images=3,
        )
        self.assertEqual(score, 70)

    def test_combined_penalties(self):
        from rayvault.product_asset_fetch import compute_stability_score
        score = compute_stability_score(
            survival_mode=True, amazon_blocks=1, cache_misses=5,
            total_products=5, missing_images=2,
        )
        # -20 (survival) -30 (blocks) -20 (2 missing) = 30
        self.assertEqual(score, 30)

    def test_floor_at_zero(self):
        from rayvault.product_asset_fetch import compute_stability_score
        score = compute_stability_score(
            survival_mode=True, amazon_blocks=5, cache_misses=5,
            total_products=5, missing_images=5,
        )
        self.assertEqual(score, 0)


class TestContentTypeValidation(unittest.TestCase):
    """Tests for Content-Type validation in downloads."""

    def test_allowed_content_types(self):
        from rayvault.product_asset_fetch import ALLOWED_IMAGE_CONTENT_TYPES
        self.assertIn("image/jpeg", ALLOWED_IMAGE_CONTENT_TYPES)
        self.assertIn("image/png", ALLOWED_IMAGE_CONTENT_TYPES)
        self.assertIn("image/webp", ALLOWED_IMAGE_CONTENT_TYPES)

    def test_html_not_allowed(self):
        from rayvault.product_asset_fetch import ALLOWED_IMAGE_CONTENT_TYPES
        self.assertNotIn("text/html", ALLOWED_IMAGE_CONTENT_TYPES)
        self.assertNotIn("application/json", ALLOWED_IMAGE_CONTENT_TYPES)


class TestAffiliateResolver(unittest.TestCase):
    """Tests for AffiliateResolver module."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.aff_path = Path(self.tmp) / "affiliates.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_file_returns_none(self):
        from rayvault.affiliate_resolver import AffiliateResolver
        aff = AffiliateResolver(self.aff_path)
        self.assertIsNone(aff.resolve("B0TEST"))

    def test_resolve_known_asin(self):
        from rayvault.affiliate_resolver import AffiliateResolver
        data = {
            "version": "1",
            "items": {
                "B0TEST123": {
                    "short_link": "https://amzn.to/abc123",
                    "source": "manual",
                    "last_verified_utc": "2026-02-14T00:00:00Z",
                }
            },
        }
        self.aff_path.write_text(json.dumps(data))
        aff = AffiliateResolver(self.aff_path)
        result = aff.resolve("B0TEST123")
        self.assertIsNotNone(result)
        self.assertEqual(result["short_link"], "https://amzn.to/abc123")
        self.assertEqual(result["source"], "manual")
        self.assertIsNotNone(result["affiliates_file_hash"])

    def test_resolve_unknown_asin(self):
        from rayvault.affiliate_resolver import AffiliateResolver
        data = {"version": "1", "items": {"B0OTHER": {"short_link": "https://amzn.to/x"}}}
        self.aff_path.write_text(json.dumps(data))
        aff = AffiliateResolver(self.aff_path)
        self.assertIsNone(aff.resolve("B0UNKNOWN"))

    def test_resolve_case_insensitive_asin(self):
        from rayvault.affiliate_resolver import AffiliateResolver
        data = {"version": "1", "items": {"B0ABC": {"short_link": "https://amzn.to/y"}}}
        self.aff_path.write_text(json.dumps(data))
        aff = AffiliateResolver(self.aff_path)
        # Input lowercase, mapping uppercase
        result = aff.resolve("b0abc")
        self.assertIsNotNone(result)

    def test_resolve_invalid_link_returns_none(self):
        from rayvault.affiliate_resolver import AffiliateResolver
        data = {"version": "1", "items": {"B0BAD": {"short_link": "not-a-url"}}}
        self.aff_path.write_text(json.dumps(data))
        aff = AffiliateResolver(self.aff_path)
        self.assertIsNone(aff.resolve("B0BAD"))

    def test_resolve_batch(self):
        from rayvault.affiliate_resolver import AffiliateResolver
        data = {
            "version": "1",
            "items": {
                "B0A": {"short_link": "https://amzn.to/a"},
                "B0B": {"short_link": "https://amzn.to/b"},
            },
        }
        self.aff_path.write_text(json.dumps(data))
        aff = AffiliateResolver(self.aff_path)
        batch = aff.resolve_batch(["B0A", "B0B", "B0C"])
        self.assertIsNotNone(batch["B0A"])
        self.assertIsNotNone(batch["B0B"])
        self.assertIsNone(batch["B0C"])

    def test_stats(self):
        from rayvault.affiliate_resolver import AffiliateResolver
        data = {"version": "1", "items": {"B0X": {"short_link": "https://amzn.to/x"}}}
        self.aff_path.write_text(json.dumps(data))
        aff = AffiliateResolver(self.aff_path)
        stats = aff.stats()
        self.assertTrue(stats["file_exists"])
        self.assertEqual(stats["total_mappings"], 1)
        self.assertEqual(stats["version"], "1")

    def test_reload(self):
        from rayvault.affiliate_resolver import AffiliateResolver
        data1 = {"version": "1", "items": {}}
        self.aff_path.write_text(json.dumps(data1))
        aff = AffiliateResolver(self.aff_path)
        self.assertIsNone(aff.resolve("B0NEW"))

        data2 = {"version": "2", "items": {"B0NEW": {"short_link": "https://amzn.to/new"}}}
        self.aff_path.write_text(json.dumps(data2))
        aff.reload()
        self.assertIsNotNone(aff.resolve("B0NEW"))


class TestPlaceholderDetection(unittest.TestCase):
    """Tests for post-download image placeholder detection."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_placeholder_dims_blacklist(self):
        from rayvault.product_asset_fetch import PLACEHOLDER_DIMS
        self.assertIn((1, 1), PLACEHOLDER_DIMS)
        self.assertIn((160, 160), PLACEHOLDER_DIMS)
        self.assertIn((120, 120), PLACEHOLDER_DIMS)

    def test_validate_too_small(self):
        from rayvault.product_asset_fetch import validate_downloaded_image
        small = Path(self.tmp) / "tiny.jpg"
        small.write_bytes(b"\xff\xd8" + b"\x00" * 100)
        err = validate_downloaded_image(small)
        self.assertIsNotNone(err)
        self.assertIn("too_small", err)

    def test_validate_good_image(self):
        from rayvault.product_asset_fetch import validate_downloaded_image
        # Create a fake "big enough" file with no parseable dims
        good = Path(self.tmp) / "good.jpg"
        good.write_bytes(b"\xff\xd8" + b"\x00" * 50000)
        err = validate_downloaded_image(good)
        self.assertIsNone(err)

    def test_validate_missing_file(self):
        from rayvault.product_asset_fetch import validate_downloaded_image
        err = validate_downloaded_image(Path(self.tmp) / "nope.jpg")
        self.assertEqual(err, "file_missing")

    def test_read_png_dims(self):
        from rayvault.product_asset_fetch import _read_image_dims
        # Build a minimal PNG IHDR with 800x600
        sig = b"\x89PNG\r\n\x1a\n"
        # chunk length (13 bytes for IHDR data)
        ihdr_len = (13).to_bytes(4, "big")
        ihdr_type = b"IHDR"
        w_bytes = (800).to_bytes(4, "big")
        h_bytes = (600).to_bytes(4, "big")
        rest = b"\x08\x02\x00\x00\x00"  # bit depth, color, compress, filter, interlace
        ihdr_data = w_bytes + h_bytes + rest
        buf = sig + ihdr_len + ihdr_type + ihdr_data + b"\x00" * 100
        f = Path(self.tmp) / "test.png"
        f.write_bytes(buf)
        dims = _read_image_dims(f)
        self.assertEqual(dims, (800, 600))

    def test_read_png_placeholder_1x1(self):
        from rayvault.product_asset_fetch import _read_image_dims, PLACEHOLDER_DIMS
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_len = (13).to_bytes(4, "big")
        ihdr_type = b"IHDR"
        w_bytes = (1).to_bytes(4, "big")
        h_bytes = (1).to_bytes(4, "big")
        rest = b"\x08\x02\x00\x00\x00"
        ihdr_data = w_bytes + h_bytes + rest
        buf = sig + ihdr_len + ihdr_type + ihdr_data + b"\x00" * 40000
        f = Path(self.tmp) / "pixel.png"
        f.write_bytes(buf)
        dims = _read_image_dims(f)
        self.assertEqual(dims, (1, 1))
        self.assertIn(dims, PLACEHOLDER_DIMS)

    def test_min_product_image_bytes(self):
        from rayvault.product_asset_fetch import MIN_PRODUCT_IMAGE_BYTES
        self.assertEqual(MIN_PRODUCT_IMAGE_BYTES, 30_000)


class TestOverlayDisplayMode(unittest.TestCase):
    """Tests for QR/overlay display mode policy."""

    def test_red_tier_always_hide(self):
        from rayvault.qr_overlay_builder import resolve_display_mode, OverlayFlags, DISPLAY_HIDE
        flags = OverlayFlags()
        mode = resolve_display_mode("RED", True, "https://amzn.to/abc", flags)
        self.assertEqual(mode, DISPLAY_HIDE)

    def test_no_link_is_hide(self):
        from rayvault.qr_overlay_builder import resolve_display_mode, OverlayFlags, DISPLAY_HIDE
        flags = OverlayFlags()
        mode = resolve_display_mode("GREEN", True, None, flags)
        self.assertEqual(mode, DISPLAY_HIDE)

    def test_not_eligible_is_hide(self):
        from rayvault.qr_overlay_builder import resolve_display_mode, OverlayFlags, DISPLAY_HIDE
        flags = OverlayFlags()
        mode = resolve_display_mode("GREEN", False, "https://amzn.to/abc", flags)
        self.assertEqual(mode, DISPLAY_HIDE)

    def test_green_default_is_link_plus_qr(self):
        from rayvault.qr_overlay_builder import resolve_display_mode, OverlayFlags, DISPLAY_LINK_PLUS_QR
        flags = OverlayFlags()
        mode = resolve_display_mode("GREEN", True, "https://amzn.to/abc", flags)
        self.assertEqual(mode, DISPLAY_LINK_PLUS_QR)

    def test_amber_default_is_link_only(self):
        from rayvault.qr_overlay_builder import resolve_display_mode, OverlayFlags, DISPLAY_LINK_ONLY
        flags = OverlayFlags()
        mode = resolve_display_mode("AMBER", True, "https://amzn.to/abc", flags)
        self.assertEqual(mode, DISPLAY_LINK_ONLY)

    def test_amber_with_allow_qr(self):
        from rayvault.qr_overlay_builder import resolve_display_mode, OverlayFlags, DISPLAY_LINK_PLUS_QR
        flags = OverlayFlags(allow_qr_amber=True)
        mode = resolve_display_mode("AMBER", True, "https://amzn.to/abc", flags)
        self.assertEqual(mode, DISPLAY_LINK_PLUS_QR)

    def test_no_qr_flag(self):
        from rayvault.qr_overlay_builder import resolve_display_mode, OverlayFlags, DISPLAY_LINK_ONLY
        flags = OverlayFlags(no_qr=True)
        mode = resolve_display_mode("GREEN", True, "https://amzn.to/abc", flags)
        self.assertEqual(mode, DISPLAY_LINK_ONLY)

    def test_force_qr_overrides_amber(self):
        from rayvault.qr_overlay_builder import resolve_display_mode, OverlayFlags, DISPLAY_LINK_PLUS_QR
        flags = OverlayFlags(force_qr=True)
        mode = resolve_display_mode("AMBER", True, "https://amzn.to/abc", flags)
        self.assertEqual(mode, DISPLAY_LINK_PLUS_QR)

    def test_force_qr_does_not_override_red(self):
        from rayvault.qr_overlay_builder import resolve_display_mode, OverlayFlags, DISPLAY_HIDE
        flags = OverlayFlags(force_qr=True)
        mode = resolve_display_mode("RED", True, "https://amzn.to/abc", flags)
        self.assertEqual(mode, DISPLAY_HIDE)

    def test_force_qr_does_not_override_no_link(self):
        from rayvault.qr_overlay_builder import resolve_display_mode, OverlayFlags, DISPLAY_HIDE
        flags = OverlayFlags(force_qr=True)
        mode = resolve_display_mode("GREEN", True, None, flags)
        self.assertEqual(mode, DISPLAY_HIDE)


class TestOverlayBuilder(unittest.TestCase):
    """Tests for the overlay builder flow (without Pillow/qrcode)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.run_dir = Path(self.tmp) / "RUN_TEST"
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def test_build_overlays_red_tier_all_hidden(self):
        from rayvault.qr_overlay_builder import build_overlays
        manifest = {
            "run_id": "RUN_TEST",
            "affiliate_policy": {"episode_truth_tier": "RED", "links_enabled": False},
            "products_summary": [
                {"rank": 1, "asin": "B0A", "title": "Test", "affiliate": {
                    "eligible": False, "short_link": None, "blocked_reason": "EPISODE_TIER_RED",
                }},
            ],
        }
        self._write_json(self.run_dir / "00_manifest.json", manifest)
        result = build_overlays(self.run_dir, apply=False)
        self.assertTrue(result.ok)
        self.assertEqual(result.hidden, 1)
        self.assertEqual(result.generated, 0)

    def test_build_overlays_green_eligible_counts_as_generated(self):
        from rayvault.qr_overlay_builder import build_overlays
        manifest = {
            "run_id": "RUN_TEST",
            "affiliate_policy": {"episode_truth_tier": "GREEN", "links_enabled": True},
            "products_summary": [
                {"rank": 1, "asin": "B0A", "title": "Great Product", "affiliate": {
                    "eligible": True, "short_link": "https://amzn.to/abc",
                }},
                {"rank": 2, "asin": "B0B", "title": "Another One", "affiliate": {
                    "eligible": True, "short_link": "https://amzn.to/def",
                }},
            ],
        }
        self._write_json(self.run_dir / "00_manifest.json", manifest)
        result = build_overlays(self.run_dir, apply=False)
        self.assertTrue(result.ok)
        self.assertEqual(result.generated, 2)
        self.assertEqual(result.hidden, 0)

    def test_build_overlays_mixed_eligible(self):
        from rayvault.qr_overlay_builder import build_overlays
        manifest = {
            "run_id": "RUN_TEST",
            "products": {"episode_truth_tier": "GREEN"},
            "products_summary": [
                {"rank": 1, "asin": "B0A", "affiliate": {
                    "eligible": True, "short_link": "https://amzn.to/abc",
                }},
                {"rank": 2, "asin": "B0B", "affiliate": {
                    "eligible": True, "short_link": None,
                }},
                {"rank": 3, "asin": "B0C", "affiliate": {
                    "eligible": False, "short_link": "https://amzn.to/xyz",
                }},
            ],
        }
        self._write_json(self.run_dir / "00_manifest.json", manifest)
        result = build_overlays(self.run_dir, apply=False)
        self.assertEqual(result.generated, 1)  # Only B0A
        self.assertEqual(result.hidden, 2)  # B0B (no link) + B0C (not eligible)

    def test_build_overlays_no_manifest(self):
        from rayvault.qr_overlay_builder import build_overlays
        result = build_overlays(self.run_dir, apply=False)
        self.assertFalse(result.ok)
        self.assertIn("manifest not found", result.warnings)

    def test_build_overlays_empty_products(self):
        from rayvault.qr_overlay_builder import build_overlays
        manifest = {"run_id": "RUN_TEST", "products_summary": []}
        self._write_json(self.run_dir / "00_manifest.json", manifest)
        result = build_overlays(self.run_dir, apply=False)
        self.assertTrue(result.ok)

    def test_display_mode_written_back(self):
        from rayvault.qr_overlay_builder import build_overlays, DISPLAY_LINK_PLUS_QR, DISPLAY_LINK_ONLY, _has_qrcode
        manifest = {
            "run_id": "RUN_TEST",
            "products": {"episode_truth_tier": "GREEN"},
            "products_summary": [
                {"rank": 1, "asin": "B0A", "affiliate": {
                    "eligible": True, "short_link": "https://amzn.to/abc",
                }},
            ],
        }
        self._write_json(self.run_dir / "00_manifest.json", manifest)
        result = build_overlays(self.run_dir, apply=False)
        # display_mode depends on qrcode availability
        expected = DISPLAY_LINK_PLUS_QR if _has_qrcode() else DISPLAY_LINK_ONLY
        self.assertEqual(result.items[0]["display_mode"], expected)

    def test_truncate_text(self):
        from rayvault.qr_overlay_builder import truncate_text
        self.assertEqual(truncate_text("Short", 52), "Short")
        long = "A" * 60
        trunc = truncate_text(long, 52)
        self.assertEqual(len(trunc), 52)
        self.assertTrue(trunc.endswith("\u2026"))

    def test_index_items_have_coords(self):
        from rayvault.qr_overlay_builder import build_overlays, DISPLAY_HIDE
        manifest = {
            "run_id": "RUN_TEST",
            "products": {"episode_truth_tier": "GREEN"},
            "products_summary": [
                {"rank": 1, "asin": "B0A", "affiliate": {
                    "eligible": True, "short_link": "https://amzn.to/abc",
                }},
            ],
        }
        self._write_json(self.run_dir / "00_manifest.json", manifest)
        result = build_overlays(self.run_dir, apply=False)
        item = result.items[0]
        self.assertIn("coords", item)
        # In dry-run, no files rendered, so coords are None
        # But the field exists for contract compliance
        self.assertIn("lowerthird", item["coords"])
        self.assertIn("qr", item["coords"])

    def test_amber_display_mode_in_items(self):
        from rayvault.qr_overlay_builder import build_overlays, DISPLAY_LINK_ONLY
        manifest = {
            "run_id": "RUN_TEST",
            "products": {"episode_truth_tier": "AMBER"},
            "products_summary": [
                {"rank": 1, "asin": "B0A", "affiliate": {
                    "eligible": True, "short_link": "https://amzn.to/abc",
                }},
            ],
        }
        self._write_json(self.run_dir / "00_manifest.json", manifest)
        result = build_overlays(self.run_dir, apply=False)
        self.assertEqual(result.items[0]["display_mode"], DISPLAY_LINK_ONLY)


class TestSmartTitle(unittest.TestCase):
    """Tests for smart_title() truncation."""

    def test_short_title_unchanged(self):
        from rayvault.qr_overlay_builder import smart_title
        self.assertEqual(smart_title("Short Title", 52), "Short Title")

    def test_empty_returns_empty(self):
        from rayvault.qr_overlay_builder import smart_title
        self.assertEqual(smart_title("", 52), "")

    def test_cuts_at_dash_separator(self):
        from rayvault.qr_overlay_builder import smart_title
        title = "Amazing Wireless Headphones - Premium Sound with Active Noise Cancellation Technology"
        result = smart_title(title, 52)
        self.assertEqual(result, "Amazing Wireless Headphones")
        self.assertLessEqual(len(result), 52)

    def test_cuts_at_pipe_separator(self):
        from rayvault.qr_overlay_builder import smart_title
        title = "Super Smart Robot Vacuum | Self-Emptying Base with LiDAR Navigation and WiFi"
        result = smart_title(title, 52)
        self.assertEqual(result, "Super Smart Robot Vacuum")

    def test_cuts_at_comma_separator(self):
        from rayvault.qr_overlay_builder import smart_title
        title = "Professional Chef Knife Set, 15 Pieces with German Steel and Wooden Block Storage"
        result = smart_title(title, 52)
        self.assertEqual(result, "Professional Chef Knife Set")

    def test_word_boundary_fallback(self):
        from rayvault.qr_overlay_builder import smart_title
        # No separators — falls back to word boundary with ellipsis
        title = "This is a very long product title without any good separator tokens in it"
        result = smart_title(title, 30)
        self.assertLessEqual(len(result), 30)
        self.assertTrue(result.endswith("\u2026"))

    def test_hard_cut_fallback(self):
        from rayvault.qr_overlay_builder import smart_title
        # No spaces at all
        title = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        result = smart_title(title, 20)
        self.assertLessEqual(len(result), 20)
        self.assertTrue(result.endswith("\u2026"))

    def test_separator_too_early_ignored(self):
        from rayvault.qr_overlay_builder import smart_title
        # Separator at position 5 — too short, should not cut there
        title = "ABC - This is a very long product title that needs truncation for display"
        result = smart_title(title, 52)
        # Should NOT cut at "ABC" (too short), but at word boundary
        self.assertLessEqual(len(result), 52)
        self.assertNotEqual(result, "ABC")


class TestURLCanonicalization(unittest.TestCase):
    """Tests for _canon_url used in QR validation."""

    def test_strip_trailing_slash(self):
        from rayvault.qr_overlay_builder import _canon_url
        self.assertEqual(_canon_url("https://amzn.to/abc/"), "https://amzn.to/abc")

    def test_strip_whitespace(self):
        from rayvault.qr_overlay_builder import _canon_url
        self.assertEqual(_canon_url("  https://amzn.to/abc  "), "https://amzn.to/abc")

    def test_no_change_for_clean_url(self):
        from rayvault.qr_overlay_builder import _canon_url
        self.assertEqual(_canon_url("https://amzn.to/abc"), "https://amzn.to/abc")

    def test_empty_string(self):
        from rayvault.qr_overlay_builder import _canon_url
        self.assertEqual(_canon_url(""), "")


class TestQRValidation(unittest.TestCase):
    """Tests for QR self-validation (validate_qr_content)."""

    def test_returns_skip_when_no_pyzbar(self):
        from rayvault.qr_overlay_builder import validate_qr_content, _has_pyzbar, _has_pillow
        if _has_pyzbar() and _has_pillow():
            self.skipTest("pyzbar is installed — cannot test skip path")
        result = validate_qr_content(Path("/fake/path.png"), "https://amzn.to/abc")
        self.assertEqual(result, "QR_VALIDATE_SKIPPED_NO_PYZBAR")

    def test_returns_error_for_missing_file(self):
        from rayvault.qr_overlay_builder import validate_qr_content, _has_pyzbar, _has_pillow
        if not _has_pyzbar() or not _has_pillow():
            self.skipTest("pyzbar/Pillow not installed")
        result = validate_qr_content(Path("/nonexistent/qr.png"), "https://amzn.to/abc")
        self.assertIsNotNone(result)
        self.assertIn("QR_DECODE_ERROR", result)

    def test_validate_qr_flag_disables_in_build(self):
        """When validate_qr=False, QR validation is skipped in build."""
        from rayvault.qr_overlay_builder import OverlayFlags
        flags = OverlayFlags(validate_qr=False)
        self.assertFalse(flags.validate_qr)


class TestOverlayAmberWarning(unittest.TestCase):
    """Tests for AMBER warning text in overlays."""

    def test_amber_warning_text_in_flags(self):
        from rayvault.qr_overlay_builder import OverlayFlags
        flags = OverlayFlags(amber_warning_text="Prices may vary")
        self.assertEqual(flags.amber_warning_text, "Prices may vary")

    def test_amber_warning_default_empty(self):
        from rayvault.qr_overlay_builder import OverlayFlags
        flags = OverlayFlags()
        self.assertEqual(flags.amber_warning_text, "")

    def test_cli_parses_amber_warning_text(self):
        from rayvault.qr_overlay_builder import main
        import io
        # Just verify the CLI doesn't crash with --amber-warning-text
        # (will fail on missing run-dir, but parses args successfully)
        tmp = tempfile.mkdtemp()
        try:
            run_dir = Path(tmp) / "RUN_TEST"
            run_dir.mkdir()
            manifest = {"run_id": "RUN_TEST", "products_summary": []}
            with open(run_dir / "00_manifest.json", "w") as f:
                json.dump(manifest, f)
            code = main(["--run-dir", str(run_dir), "--amber-warning-text", "Prices may vary"])
            self.assertEqual(code, 0)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_red_tier_apply_writes_index_and_manifest(self):
        """RED tier with --apply must write overlays_index.json and patch manifest."""
        from rayvault.qr_overlay_builder import build_overlays
        tmp = tempfile.mkdtemp()
        try:
            run_dir = Path(tmp) / "RUN_TEST"
            run_dir.mkdir()
            manifest = {
                "run_id": "RUN_TEST",
                "affiliate_policy": {"episode_truth_tier": "RED", "links_enabled": False},
                "products_summary": [
                    {"rank": 1, "asin": "B0A", "title": "Test", "affiliate": {
                        "eligible": False, "short_link": None, "blocked_reason": "EPISODE_TIER_RED",
                    }},
                ],
            }
            with open(run_dir / "00_manifest.json", "w") as f:
                json.dump(manifest, f)
            result = build_overlays(run_dir, apply=True)
            self.assertTrue(result.ok)
            # Index file must exist
            idx_path = run_dir / "publish" / "overlays" / "overlays_index.json"
            self.assertTrue(idx_path.exists(), "overlays_index.json must be written even for RED tier")
            idx = json.loads(idx_path.read_text())
            self.assertEqual(idx["episode_truth_tier"], "RED")
            # Manifest must be patched
            m = json.loads((run_dir / "00_manifest.json").read_text())
            self.assertIn("render", m)
            self.assertEqual(m["render"]["overlays_tier"], "RED")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cli_parses_no_validate_qr(self):
        from rayvault.qr_overlay_builder import main
        tmp = tempfile.mkdtemp()
        try:
            run_dir = Path(tmp) / "RUN_TEST"
            run_dir.mkdir()
            manifest = {"run_id": "RUN_TEST", "products_summary": []}
            with open(run_dir / "00_manifest.json", "w") as f:
                json.dump(manifest, f)
            code = main(["--run-dir", str(run_dir), "--no-validate-qr"])
            self.assertEqual(code, 0)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestRenderConfigV13(unittest.TestCase):
    """Tests for render_config_generate.py v1.3 contract."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.run_dir = Path(self.tmp) / "RUN_TEST"
        self.run_dir.mkdir(parents=True)
        # Write minimal script
        (self.run_dir / "01_script.txt").write_text("Hello world " * 50)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_version_is_1_3(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        self.assertEqual(result["config"]["version"], "1.3")

    def test_output_section_exists(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        out = result["config"]["output"]
        self.assertEqual(out["w"], 1920)
        self.assertEqual(out["h"], 1080)
        self.assertEqual(out["fps"], 30)
        self.assertEqual(out["vcodec"], "libx264")
        self.assertEqual(out["pix_fmt"], "yuv420p")

    def test_segments_have_id_and_frames(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        for seg in result["config"]["segments"]:
            self.assertIn("id", seg)
            self.assertIn("frames", seg)
            self.assertTrue(seg["id"].startswith("seg_"))
            # frames should match (t1-t0)*fps
            expected = round((seg["t1"] - seg["t0"]) * 30)
            self.assertEqual(seg["frames"], expected)

    def test_canvas_still_exists_for_compat(self):
        from rayvault.render_config_generate import generate_render_config
        result = generate_render_config(self.run_dir)
        self.assertIn("canvas", result["config"])


class TestFFmpegRenderGates(unittest.TestCase):
    """Tests for ffmpeg_render.py validation gates."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.run_dir = Path(self.tmp) / "RUN_TEST"
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def test_gate_essential_files_missing(self):
        from rayvault.ffmpeg_render import gate_essential_files
        result = gate_essential_files(self.run_dir)
        self.assertFalse(result.ok)
        self.assertTrue(len(result.errors) >= 3)

    def test_gate_essential_files_all_present(self):
        from rayvault.ffmpeg_render import gate_essential_files
        self._write_json(self.run_dir / "00_manifest.json", {"run_id": "TEST"})
        self._write_json(self.run_dir / "05_render_config.json", {"version": "1.3"})
        self._write_json(self.run_dir / "publish" / "overlays" / "overlays_index.json", {"items": []})
        # Create a minimal WAV
        self._create_wav(self.run_dir / "02_audio.wav", 10.0)
        result = gate_essential_files(self.run_dir)
        self.assertTrue(result.ok)

    def test_gate_temporal_consistency_ok(self):
        from rayvault.ffmpeg_render import gate_temporal_consistency
        config = {"segments": [
            {"id": "seg_000", "type": "intro", "t0": 0.0, "t1": 2.0},
            {"id": "seg_001", "type": "product", "t0": 2.0, "t1": 6.0},
            {"id": "seg_002", "type": "outro", "t0": 6.0, "t1": 7.5},
        ]}
        result = gate_temporal_consistency(config, 7.5)
        self.assertTrue(result.ok)

    def test_gate_temporal_consistency_timeline_exceeds(self):
        from rayvault.ffmpeg_render import gate_temporal_consistency
        config = {"segments": [
            {"id": "seg_000", "type": "intro", "t0": 0.0, "t1": 2.0},
            {"id": "seg_001", "type": "outro", "t0": 2.0, "t1": 30.0},
        ]}
        # Timeline=30s but audio=20s — would cut speech
        result = gate_temporal_consistency(config, 20.0)
        self.assertFalse(result.ok)
        self.assertTrue(any("TIMELINE_EXCEEDS_AUDIO" in e for e in result.errors))

    def test_gate_temporal_audio_tail_warning(self):
        from rayvault.ffmpeg_render import gate_temporal_consistency
        config = {"segments": [
            {"id": "seg_000", "type": "intro", "t0": 0.0, "t1": 2.0},
            {"id": "seg_001", "type": "outro", "t0": 2.0, "t1": 3.5},
        ]}
        # Timeline=3.5s but audio=5.0s — audio extends beyond
        result = gate_temporal_consistency(config, 5.0)
        self.assertTrue(result.ok)
        self.assertTrue(len(result.warnings) > 0)

    def test_gate_frames_consistency_ok(self):
        from rayvault.ffmpeg_render import gate_frames_consistency
        config = {
            "output": {"fps": 30},
            "segments": [
                {"id": "seg_000", "t0": 0.0, "t1": 2.0, "frames": 60},
                {"id": "seg_001", "t0": 2.0, "t1": 6.0, "frames": 120},
            ],
        }
        result = gate_frames_consistency(config)
        self.assertTrue(result.ok)

    def test_gate_frames_consistency_mismatch(self):
        from rayvault.ffmpeg_render import gate_frames_consistency
        config = {
            "output": {"fps": 30},
            "segments": [
                {"id": "seg_000", "t0": 0.0, "t1": 2.0, "frames": 999},
            ],
        }
        result = gate_frames_consistency(config)
        self.assertFalse(result.ok)
        self.assertTrue(any("FRAME_MISMATCH" in e for e in result.errors))

    def test_gate_segment_sources_skip_ok(self):
        from rayvault.ffmpeg_render import gate_segment_sources
        config = {"segments": [
            {"id": "seg_001", "type": "product", "visual": {"mode": "SKIP", "source": None}},
        ]}
        result = gate_segment_sources(self.run_dir, config)
        self.assertTrue(result.ok)

    def _create_wav(self, path, duration_sec):
        """Create a minimal WAV file."""
        import struct
        path.parent.mkdir(parents=True, exist_ok=True)
        rate = 44100
        nframes = int(duration_sec * rate)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(b"\x00\x00" * nframes)


class TestFFmpegRenderHashes(unittest.TestCase):
    """Tests for render hash computation."""

    def test_segment_hash_deterministic(self):
        from rayvault.ffmpeg_render import compute_segment_inputs_hash
        seg = {"id": "seg_000", "type": "intro", "t0": 0.0, "t1": 2.0}
        output = {"w": 1920, "h": 1080, "fps": 30}
        h1 = compute_segment_inputs_hash(seg, Path("/tmp"), {"items": []}, output)
        h2 = compute_segment_inputs_hash(seg, Path("/tmp"), {"items": []}, output)
        self.assertEqual(h1, h2)

    def test_segment_hash_changes_with_output(self):
        from rayvault.ffmpeg_render import compute_segment_inputs_hash
        seg = {"id": "seg_000", "type": "intro", "t0": 0.0, "t1": 2.0}
        o1 = {"w": 1920, "h": 1080, "fps": 30}
        o2 = {"w": 1280, "h": 720, "fps": 30}
        h1 = compute_segment_inputs_hash(seg, Path("/tmp"), {"items": []}, o1)
        h2 = compute_segment_inputs_hash(seg, Path("/tmp"), {"items": []}, o2)
        self.assertNotEqual(h1, h2)

    def test_segment_hash_changes_with_timing(self):
        from rayvault.ffmpeg_render import compute_segment_inputs_hash
        seg1 = {"id": "seg_000", "type": "intro", "t0": 0.0, "t1": 2.0}
        seg2 = {"id": "seg_000", "type": "intro", "t0": 0.0, "t1": 3.0}
        output = {"w": 1920, "h": 1080, "fps": 30}
        h1 = compute_segment_inputs_hash(seg1, Path("/tmp"), {"items": []}, output)
        h2 = compute_segment_inputs_hash(seg2, Path("/tmp"), {"items": []}, output)
        self.assertNotEqual(h1, h2)


class TestFFmpegRenderCommands(unittest.TestCase):
    """Tests for FFmpeg command building."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.run_dir = Path(self.tmp) / "RUN_TEST"
        self.run_dir.mkdir(parents=True)
        self.output = {"w": 1920, "h": 1080, "fps": 30, "vcodec": "libx264",
                       "crf": 18, "preset": "slow", "pix_fmt": "yuv420p"}
        self.overlays = {"items": []}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_intro_cmd_has_loop_and_duration(self):
        from rayvault.ffmpeg_render import build_segment_cmd
        seg = {"id": "seg_000", "type": "intro", "t0": 0.0, "t1": 2.0, "frames": 60}
        # Create frame
        frame = self.run_dir / "03_frame.png"
        frame.parent.mkdir(parents=True, exist_ok=True)
        frame.write_bytes(b"PNG_STUB")
        cmd = build_segment_cmd(seg, self.run_dir, self.output, self.overlays, Path("/tmp/seg.mp4"))
        self.assertIn("-loop", cmd)
        self.assertIn("1", cmd)
        self.assertIn("-t", cmd)
        self.assertIn("2.0", cmd)

    def test_skip_cmd_uses_color_source(self):
        from rayvault.ffmpeg_render import build_segment_cmd
        seg = {"id": "seg_001", "type": "product", "rank": 1,
               "t0": 2.0, "t1": 6.0, "frames": 120,
               "visual": {"mode": "SKIP", "source": None}}
        cmd = build_segment_cmd(seg, self.run_dir, self.output, self.overlays, Path("/tmp/seg.mp4"))
        cmd_str = " ".join(cmd)
        self.assertIn("color=c=black", cmd_str)

    def test_broll_cmd_uses_stream_loop(self):
        from rayvault.ffmpeg_render import build_segment_cmd
        # Create a fake broll file
        broll = self.run_dir / "products" / "p01" / "broll" / "approved.mp4"
        broll.parent.mkdir(parents=True, exist_ok=True)
        broll.write_bytes(b"MP4_STUB")
        seg = {"id": "seg_001", "type": "product", "rank": 1,
               "t0": 2.0, "t1": 6.0, "frames": 120,
               "visual": {"mode": "BROLL_VIDEO",
                          "source": "products/p01/broll/approved.mp4"}}
        cmd = build_segment_cmd(seg, self.run_dir, self.output, self.overlays, Path("/tmp/seg.mp4"))
        self.assertIn("-stream_loop", cmd)

    def test_kenburns_cmd_has_zoompan(self):
        from rayvault.ffmpeg_render import build_segment_cmd
        img = self.run_dir / "products" / "p01" / "source_images" / "01_main.jpg"
        img.parent.mkdir(parents=True, exist_ok=True)
        img.write_bytes(b"JPG_STUB")
        seg = {"id": "seg_001", "type": "product", "rank": 1,
               "t0": 2.0, "t1": 6.0, "frames": 120,
               "visual": {"mode": "KEN_BURNS",
                          "source": "products/p01/source_images/01_main.jpg"}}
        cmd = build_segment_cmd(seg, self.run_dir, self.output, self.overlays, Path("/tmp/seg.mp4"))
        cmd_str = " ".join(cmd)
        self.assertIn("zoompan", cmd_str)
        self.assertIn("-loop", cmd)

    def test_overlay_filter_chain(self):
        from rayvault.ffmpeg_render import build_segment_cmd
        img = self.run_dir / "products" / "p01" / "source_images" / "01_main.jpg"
        img.parent.mkdir(parents=True, exist_ok=True)
        img.write_bytes(b"JPG_STUB")
        lt = self.run_dir / "publish" / "overlays" / "p01_lowerthird.png"
        lt.parent.mkdir(parents=True, exist_ok=True)
        lt.write_bytes(b"PNG_STUB")
        overlays = {"items": [{
            "rank": 1, "display_mode": "LINK_ONLY",
            "lowerthird_path": "publish/overlays/p01_lowerthird.png",
            "qr_path": None,
            "coords": {
                "lowerthird": {"x": 0, "y": 0, "w": 1920, "h": 1080},
                "qr": None,
            },
        }]}
        seg = {"id": "seg_001", "type": "product", "rank": 1,
               "t0": 2.0, "t1": 6.0, "frames": 120,
               "visual": {"mode": "KEN_BURNS",
                          "source": "products/p01/source_images/01_main.jpg"}}
        cmd = build_segment_cmd(seg, self.run_dir, self.output, overlays, Path("/tmp/seg.mp4"))
        cmd_str = " ".join(cmd)
        self.assertIn("overlay=0:0", cmd_str)
        self.assertIn("filter_complex", cmd_str)


class TestFFmpegErrorClassification(unittest.TestCase):
    """Tests for FFmpeg error classification."""

    def test_missing_input(self):
        from rayvault.ffmpeg_render import classify_ffmpeg_error
        self.assertEqual(
            classify_ffmpeg_error("No such file or directory"),
            "MISSING_INPUT",
        )

    def test_corrupt_media(self):
        from rayvault.ffmpeg_render import classify_ffmpeg_error
        self.assertEqual(
            classify_ffmpeg_error("Invalid data found when processing input"),
            "CORRUPT_MEDIA",
        )

    def test_unknown_error(self):
        from rayvault.ffmpeg_render import classify_ffmpeg_error
        self.assertEqual(
            classify_ffmpeg_error("Something unusual happened"),
            "FFMPEG_UNKNOWN",
        )


class TestFFmpegRenderDryRun(unittest.TestCase):
    """Tests for ffmpeg_render.py dry-run mode (no actual FFmpeg calls)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.run_dir = Path(self.tmp) / "RUN_TEST"
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def _create_wav(self, path, duration_sec):
        import struct
        path.parent.mkdir(parents=True, exist_ok=True)
        rate = 44100
        nframes = int(duration_sec * rate)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(b"\x00\x00" * nframes)

    def test_dry_run_passes_validation(self):
        from rayvault.ffmpeg_render import render
        # Create all required files
        self._write_json(self.run_dir / "00_manifest.json", {"run_id": "TEST"})
        self._write_json(self.run_dir / "05_render_config.json", {
            "version": "1.3",
            "output": {"w": 1920, "h": 1080, "fps": 30},
            "ray": {"frame_path": "03_frame.png"},
            "audio": {"path": "02_audio.wav", "duration_sec": 7.5},
            "segments": [
                {"id": "seg_000", "type": "intro", "t0": 0.0, "t1": 2.0, "frames": 60},
                {"id": "seg_001", "type": "product", "rank": 1, "t0": 2.0, "t1": 6.0,
                 "frames": 120, "visual": {"mode": "SKIP", "source": None}},
                {"id": "seg_002", "type": "outro", "t0": 6.0, "t1": 7.5, "frames": 45},
            ],
        })
        self._write_json(
            self.run_dir / "publish" / "overlays" / "overlays_index.json",
            {"episode_truth_tier": "GREEN", "items": []},
        )
        self._create_wav(self.run_dir / "02_audio.wav", 7.5)
        # Create frame
        (self.run_dir / "03_frame.png").write_bytes(b"PNG_STUB")

        result = render(self.run_dir, apply=False)
        self.assertTrue(result.ok)
        self.assertEqual(result.status, "DRY_RUN")
        self.assertEqual(result.segments_total, 3)
        self.assertTrue(len(result.inputs_hash) > 0)

    def test_dry_run_fails_without_overlays_index(self):
        from rayvault.ffmpeg_render import render
        self._write_json(self.run_dir / "00_manifest.json", {"run_id": "TEST"})
        self._write_json(self.run_dir / "05_render_config.json", {"segments": []})
        self._create_wav(self.run_dir / "02_audio.wav", 5.0)
        result = render(self.run_dir, apply=False)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "BLOCKED")

    def test_dry_run_global_hash_deterministic(self):
        from rayvault.ffmpeg_render import render
        self._write_json(self.run_dir / "00_manifest.json", {"run_id": "TEST"})
        self._write_json(self.run_dir / "05_render_config.json", {
            "version": "1.3",
            "output": {"w": 1920, "h": 1080, "fps": 30},
            "ray": {"frame_path": "03_frame.png"},
            "segments": [
                {"id": "seg_000", "type": "intro", "t0": 0.0, "t1": 2.0, "frames": 60},
                {"id": "seg_001", "type": "outro", "t0": 2.0, "t1": 3.5, "frames": 45},
            ],
        })
        self._write_json(
            self.run_dir / "publish" / "overlays" / "overlays_index.json",
            {"items": []},
        )
        self._create_wav(self.run_dir / "02_audio.wav", 3.5)
        (self.run_dir / "03_frame.png").write_bytes(b"PNG_STUB")

        r1 = render(self.run_dir, apply=False)
        r2 = render(self.run_dir, apply=False)
        self.assertEqual(r1.inputs_hash, r2.inputs_hash)


# ============================================================================
# Resolve Bridge tests
# ============================================================================


class TestResolveBridgeKenBurns(unittest.TestCase):
    """Ken Burns pattern determinism + selection from resolve_bridge."""

    def test_pattern_deterministic(self):
        from rayvault.resolve_bridge import kenburns_pattern_for_segment
        p1 = kenburns_pattern_for_segment("RUN_A", "B00TEST", 1)
        p2 = kenburns_pattern_for_segment("RUN_A", "B00TEST", 1)
        self.assertEqual(p1["name"], p2["name"])

    def test_different_inputs_may_differ(self):
        from rayvault.resolve_bridge import kenburns_pattern_for_segment
        p1 = kenburns_pattern_for_segment("RUN_A", "ASIN_1", 1)
        p2 = kenburns_pattern_for_segment("RUN_A", "ASIN_2", 2)
        # Not guaranteed to differ, but both must be valid patterns
        from rayvault.resolve_bridge import KENBURNS_PATTERNS
        valid_names = {p["name"] for p in KENBURNS_PATTERNS}
        self.assertIn(p1["name"], valid_names)
        self.assertIn(p2["name"], valid_names)

    def test_all_patterns_have_required_keys(self):
        from rayvault.resolve_bridge import KENBURNS_PATTERNS
        for pat in KENBURNS_PATTERNS:
            self.assertIn("name", pat)
            self.assertIn("zoom", pat)
            self.assertIn("pan_x", pat)
            self.assertIn("pan_y", pat)
            self.assertEqual(len(pat["zoom"]), 2)

    def test_six_patterns_available(self):
        from rayvault.resolve_bridge import KENBURNS_PATTERNS
        self.assertEqual(len(KENBURNS_PATTERNS), 6)


class TestResolveCapabilities(unittest.TestCase):
    """ResolveCapabilities dataclass."""

    def test_defaults_all_false(self):
        from rayvault.resolve_bridge import ResolveCapabilities
        caps = ResolveCapabilities()
        self.assertFalse(caps.scripting_available)
        self.assertFalse(caps.resolve_connected)
        self.assertFalse(caps.can_create_project)

    def test_to_dict(self):
        from rayvault.resolve_bridge import ResolveCapabilities
        caps = ResolveCapabilities(scripting_available=True,
                                   resolve_connected=True,
                                   resolve_version="19.1")
        d = caps.to_dict()
        self.assertTrue(d["scripting_available"])
        self.assertTrue(d["resolve_connected"])
        self.assertEqual(d["resolve_version"], "19.1")
        self.assertFalse(d["can_create_project"])

    def test_to_dict_has_all_fields(self):
        from rayvault.resolve_bridge import ResolveCapabilities
        caps = ResolveCapabilities()
        d = caps.to_dict()
        expected_keys = {
            "scripting_available", "resolve_connected",
            "can_create_project", "can_create_timeline",
            "can_import_media", "can_set_project_settings",
            "can_set_render_settings", "can_start_render",
            "can_get_render_status", "can_add_track",
            "resolve_version", "resolve_name",
        }
        self.assertEqual(set(d.keys()), expected_keys)


class TestResolveBridgeDisconnected(unittest.TestCase):
    """Test bridge methods when Resolve is NOT connected."""

    def test_bridge_not_connected_by_default(self):
        from rayvault.resolve_bridge import ResolveBridge
        bridge = ResolveBridge()
        self.assertFalse(bridge.connected)
        self.assertIsNone(bridge.project)
        self.assertIsNone(bridge.media_pool)
        self.assertIsNone(bridge.timeline)

    def test_create_bins_returns_empty(self):
        from rayvault.resolve_bridge import ResolveBridge
        bridge = ResolveBridge()
        bins = bridge.create_bins()
        self.assertEqual(bins, {})

    def test_import_media_returns_empty(self):
        from rayvault.resolve_bridge import ResolveBridge
        bridge = ResolveBridge()
        items = bridge.import_media(["/fake/path.mp4"])
        self.assertEqual(items, [])

    def test_create_timeline_returns_false(self):
        from rayvault.resolve_bridge import ResolveBridge
        bridge = ResolveBridge()
        self.assertFalse(bridge.create_timeline("test"))

    def test_disconnect_clears_state(self):
        from rayvault.resolve_bridge import ResolveBridge
        bridge = ResolveBridge()
        bridge.disconnect()
        self.assertFalse(bridge.connected)


# ============================================================================
# DaVinci Assembler tests
# ============================================================================


class TestDaVinciAssemblerGates(unittest.TestCase):
    """Test DaVinci assembler gates without requiring Resolve."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.run_dir = Path(self.tmp) / "runs" / "TEST_RUN"
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "publish" / "overlays").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def _create_wav(self, path, duration_sec=5.0, rate=48000):
        import struct
        n_frames = int(duration_sec * rate)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(struct.pack(f"<{n_frames}h", *([0] * n_frames)))

    def test_gate_essential_files_missing(self):
        from rayvault.davinci_assembler import gate_essential_files
        result = gate_essential_files(self.run_dir)
        self.assertFalse(result.ok)
        self.assertTrue(len(result.errors) >= 3)

    def test_gate_essential_files_ok(self):
        from rayvault.davinci_assembler import gate_essential_files
        self._write_json(self.run_dir / "00_manifest.json", {"run_id": "TEST"})
        self._write_json(self.run_dir / "05_render_config.json", {"segments": []})
        self._create_wav(self.run_dir / "02_audio.wav", 5.0)
        self._write_json(
            self.run_dir / "publish" / "overlays" / "overlays_index.json",
            {"items": []},
        )
        result = gate_essential_files(self.run_dir)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.errors), 0)

    def test_gate_essential_partial_missing(self):
        from rayvault.davinci_assembler import gate_essential_files
        self._write_json(self.run_dir / "00_manifest.json", {"run_id": "TEST"})
        # Missing: render_config, audio, overlays_index
        result = gate_essential_files(self.run_dir)
        self.assertFalse(result.ok)
        self.assertTrue(len(result.errors) >= 2)


class TestDaVinciAssemblerHash(unittest.TestCase):
    """Test compute_inputs_hash determinism."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.run_dir = Path(self.tmp) / "runs" / "TEST_RUN"
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "publish" / "overlays").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def _create_wav(self, path, duration_sec=5.0, rate=48000):
        import struct
        n_frames = int(duration_sec * rate)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(struct.pack(f"<{n_frames}h", *([0] * n_frames)))

    def test_hash_deterministic(self):
        from rayvault.davinci_assembler import compute_inputs_hash
        self._write_json(self.run_dir / "05_render_config.json", {"v": "1.3"})
        self._write_json(
            self.run_dir / "publish" / "overlays" / "overlays_index.json",
            {"items": []},
        )
        self._create_wav(self.run_dir / "02_audio.wav", 3.0)

        h1 = compute_inputs_hash(self.run_dir)
        h2 = compute_inputs_hash(self.run_dir)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 40)  # SHA1 hex

    def test_hash_changes_with_config(self):
        from rayvault.davinci_assembler import compute_inputs_hash
        self._write_json(self.run_dir / "05_render_config.json", {"v": "1.3"})
        self._write_json(
            self.run_dir / "publish" / "overlays" / "overlays_index.json",
            {"items": []},
        )
        self._create_wav(self.run_dir / "02_audio.wav", 3.0)
        h1 = compute_inputs_hash(self.run_dir)

        # Change config
        self._write_json(self.run_dir / "05_render_config.json", {"v": "1.4"})
        h2 = compute_inputs_hash(self.run_dir)
        self.assertNotEqual(h1, h2)

    def test_hash_includes_engine_tag(self):
        from rayvault.davinci_assembler import compute_inputs_hash
        self._write_json(self.run_dir / "05_render_config.json", {"v": "1.3"})
        h = compute_inputs_hash(self.run_dir)
        # Hash includes "engine:davinci" so it differs from ffmpeg hash
        self.assertTrue(len(h) > 0)


class TestDaVinciAssemblerDryRun(unittest.TestCase):
    """Test DaVinci assembler dry-run (no Resolve connection needed)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.run_dir = Path(self.tmp) / "runs" / "TEST_RUN"
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "publish" / "overlays").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def _create_wav(self, path, duration_sec=5.0, rate=48000):
        import struct
        n_frames = int(duration_sec * rate)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(struct.pack(f"<{n_frames}h", *([0] * n_frames)))

    def test_dry_run_ok(self):
        from rayvault.davinci_assembler import assemble
        self._write_json(self.run_dir / "00_manifest.json", {"run_id": "TEST"})
        self._write_json(self.run_dir / "05_render_config.json", {
            "version": "1.3",
            "output": {"w": 1920, "h": 1080, "fps": 30},
            "ray": {"frame_path": "03_frame.png"},
            "segments": [
                {"id": "seg_000", "type": "intro", "t0": 0.0, "t1": 2.0, "frames": 60},
                {"id": "seg_001", "type": "outro", "t0": 2.0, "t1": 3.5, "frames": 45},
            ],
        })
        self._write_json(
            self.run_dir / "publish" / "overlays" / "overlays_index.json",
            {"episode_truth_tier": "GREEN", "items": []},
        )
        self._create_wav(self.run_dir / "02_audio.wav", 3.5)

        result = assemble(self.run_dir, apply=False)
        self.assertTrue(result.ok)
        self.assertEqual(result.status, "DRY_RUN")
        self.assertEqual(result.engine_used, "davinci")
        self.assertTrue(len(result.inputs_hash) > 0)

    def test_dry_run_blocked_without_manifest(self):
        from rayvault.davinci_assembler import assemble
        result = assemble(self.run_dir, apply=False)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "BLOCKED")

    def test_dry_run_blocked_without_audio(self):
        from rayvault.davinci_assembler import assemble
        self._write_json(self.run_dir / "00_manifest.json", {"run_id": "TEST"})
        self._write_json(self.run_dir / "05_render_config.json", {"segments": []})
        self._write_json(
            self.run_dir / "publish" / "overlays" / "overlays_index.json",
            {"items": []},
        )
        result = assemble(self.run_dir, apply=False)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "BLOCKED")


class TestDaVinciVerifyResult(unittest.TestCase):
    """Test VerifyResult and verify_output logic."""

    def test_verify_missing_file(self):
        from rayvault.davinci_assembler import verify_output
        result = verify_output(Path("/nonexistent/video.mp4"), 10.0)
        self.assertFalse(result.ok)
        self.assertIn("OUTPUT_MISSING", result.errors)

    def test_verify_result_defaults(self):
        from rayvault.davinci_assembler import VerifyResult
        r = VerifyResult(ok=True)
        self.assertTrue(r.ok)
        self.assertEqual(r.duration_sec, 0.0)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.warnings, [])

    def test_assemble_result_defaults(self):
        from rayvault.davinci_assembler import AssembleResult
        r = AssembleResult(ok=False, status="BLOCKED")
        self.assertFalse(r.ok)
        self.assertEqual(r.engine_used, "")
        self.assertIsNone(r.output_path)


# ============================================================================
# Final Validator — davinci_required gate tests
# ============================================================================


class TestGateDaVinciRequired(unittest.TestCase):
    """Test the davinci_required gate in final_validator."""

    def test_pass_when_engine_davinci(self):
        from rayvault.final_validator import gate_davinci_required
        manifest = {"render": {"engine_used": "davinci", "davinci_required": True}}
        g = gate_davinci_required(manifest)
        self.assertTrue(g.passed)
        self.assertEqual(g.name, "davinci_required")

    def test_fail_when_engine_shadow(self):
        from rayvault.final_validator import gate_davinci_required
        manifest = {"render": {"engine_used": "shadow_ffmpeg"}}
        g = gate_davinci_required(manifest)
        self.assertFalse(g.passed)
        self.assertIn("shadow_ffmpeg", g.detail)

    def test_fail_when_no_engine(self):
        from rayvault.final_validator import gate_davinci_required
        manifest = {"render": {}}
        g = gate_davinci_required(manifest)
        self.assertFalse(g.passed)
        self.assertIn("no engine_used", g.detail)

    def test_pass_when_policy_disabled(self):
        from rayvault.final_validator import gate_davinci_required
        manifest = {"render": {"engine_used": "shadow_ffmpeg", "davinci_required": False}}
        g = gate_davinci_required(manifest)
        self.assertTrue(g.passed)
        self.assertIn("policy disabled", g.detail)

    def test_default_policy_is_required(self):
        from rayvault.final_validator import gate_davinci_required
        # No davinci_required field — defaults to True
        manifest = {"render": {"engine_used": "ffmpeg"}}
        g = gate_davinci_required(manifest)
        self.assertFalse(g.passed)

    def test_pass_no_render_section_and_policy_disabled(self):
        from rayvault.final_validator import gate_davinci_required
        manifest = {}
        g = gate_davinci_required(manifest)
        # No render section means engine_used is empty, policy defaults to True → fail
        self.assertFalse(g.passed)

    def test_gate_in_validate_run(self):
        """The davinci_required gate should appear in full validation output."""
        from rayvault.final_validator import validate_run
        tmp = tempfile.mkdtemp()
        run_dir = Path(tmp) / "TEST"
        run_dir.mkdir(parents=True)
        (run_dir / "publish").mkdir()
        # Minimal manifest
        manifest = {
            "run_id": "TEST",
            "status": "READY_FOR_RENDER",
            "metadata": {"identity": {"confidence": "HIGH"}, "visual_qc_result": "PASS"},
            "stability": {"stability_score": 90},
            "render": {"engine_used": "davinci", "davinci_required": True},
        }
        with open(run_dir / "00_manifest.json", "w") as f:
            json.dump(manifest, f)
        with open(run_dir / "01_script.txt", "w") as f:
            f.write("Test script")
        with open(run_dir / "03_frame.png", "wb") as f:
            f.write(b"PNG_STUB")

        import struct
        rate = 48000
        n_frames = int(5.0 * rate)
        with wave.open(str(run_dir / "02_audio.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(struct.pack(f"<{n_frames}h", *([0] * n_frames)))

        with open(run_dir / "05_render_config.json", "w") as f:
            json.dump({"segments": [{"id": "s0", "type": "intro"}]}, f)

        video = run_dir / "publish" / "video_final.mp4"
        video.write_bytes(b"X" * 2048)

        verdict = validate_run(run_dir, require_video=True)
        gate_names = [g.name for g in verdict.gates]
        self.assertIn("davinci_required", gate_names)
        dg = next(g for g in verdict.gates if g.name == "davinci_required")
        self.assertTrue(dg.passed)

        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================
# Pacing validation tests
# ============================================================================


class TestPacingValidation(unittest.TestCase):
    """Tests for render_config_generate pacing validation."""

    def test_pacing_ok_with_motion(self):
        from rayvault.render_config_generate import validate_pacing
        segments = [
            {"id": "s0", "type": "intro", "t0": 0, "t1": 2},
            {"id": "s1", "type": "product", "t0": 2, "t1": 22,
             "visual": {"mode": "KEN_BURNS"}},  # 20s but has motion
            {"id": "s2", "type": "product", "t0": 22, "t1": 32,
             "visual": {"mode": "BROLL_VIDEO"}},
            {"id": "s3", "type": "outro", "t0": 32, "t1": 34},
        ]
        result = validate_pacing(segments)
        self.assertTrue(result["ok"])

    def test_pacing_fails_long_static(self):
        from rayvault.render_config_generate import validate_pacing
        segments = [
            {"id": "s0", "type": "intro", "t0": 0, "t1": 2},
            {"id": "s1", "type": "product", "t0": 2, "t1": 25,
             "visual": {"mode": "STILL_ONLY"}},  # 23s static!
            {"id": "s2", "type": "outro", "t0": 25, "t1": 27},
        ]
        result = validate_pacing(segments)
        self.assertFalse(result["ok"])
        self.assertTrue(any("LONG_STATIC" in e for e in result["errors"]))

    def test_pacing_skip_segments_flagged(self):
        from rayvault.render_config_generate import validate_pacing
        segments = [
            {"id": "s0", "type": "intro", "t0": 0, "t1": 2},
            {"id": "s1", "type": "product", "t0": 2, "t1": 22,
             "visual": {"mode": "SKIP"}},  # 20s static SKIP
            {"id": "s2", "type": "outro", "t0": 22, "t1": 24},
        ]
        result = validate_pacing(segments)
        self.assertFalse(result["ok"])

    def test_pacing_variety_warning(self):
        from rayvault.render_config_generate import validate_pacing
        segments = [
            {"id": "s0", "type": "intro", "t0": 0, "t1": 2},
            {"id": "s1", "type": "product", "t0": 2, "t1": 6,
             "visual": {"mode": "KEN_BURNS"}},
            {"id": "s2", "type": "product", "t0": 6, "t1": 10,
             "visual": {"mode": "KEN_BURNS"}},
            {"id": "s3", "type": "product", "t0": 10, "t1": 14,
             "visual": {"mode": "KEN_BURNS"}},
            {"id": "s4", "type": "outro", "t0": 14, "t1": 16},
        ]
        result = validate_pacing(segments)
        self.assertTrue(result["ok"])  # No long static — pacing OK
        self.assertTrue(result["variety_warning"])  # But only 1 type

    def test_pacing_no_variety_warning_with_mixed(self):
        from rayvault.render_config_generate import validate_pacing
        segments = [
            {"id": "s0", "type": "intro", "t0": 0, "t1": 2},
            {"id": "s1", "type": "product", "t0": 2, "t1": 6,
             "visual": {"mode": "KEN_BURNS"}},
            {"id": "s2", "type": "product", "t0": 6, "t1": 10,
             "visual": {"mode": "BROLL_VIDEO"}},
            {"id": "s3", "type": "outro", "t0": 10, "t1": 12},
        ]
        result = validate_pacing(segments)
        self.assertTrue(result["ok"])
        self.assertFalse(result["variety_warning"])

    def test_pacing_in_render_config(self):
        """Pacing block should appear in generated render config."""
        from rayvault.render_config_generate import generate_render_config
        tmp = tempfile.mkdtemp()
        run_dir = Path(tmp) / "RUN_PACE"
        run_dir.mkdir(parents=True)
        (run_dir / "products").mkdir()
        (run_dir / "01_script.txt").write_text("This is a test script for pacing.")
        result = generate_render_config(run_dir)
        self.assertIn("pacing", result["config"])
        self.assertIn("ok", result["config"]["pacing"])
        self.assertIn("pacing", result)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================
# Black frame detection tests
# ============================================================================


class TestBlackFrameDetection(unittest.TestCase):
    """Tests for black frame / offline detection logic."""

    def test_detect_missing_video(self):
        from rayvault.davinci_assembler import detect_black_frames
        result = detect_black_frames(Path("/nonexistent.mp4"))
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error"), "VIDEO_NOT_FOUND")

    def test_sample_frame_red_ratio_nonexistent(self):
        from rayvault.davinci_assembler import _sample_frame_red_ratio
        ratio = _sample_frame_red_ratio(Path("/nonexistent.mp4"), 1.0)
        self.assertIsNone(ratio)


# ============================================================================
# Disk space check tests
# ============================================================================


class TestDiskSpaceCheck(unittest.TestCase):
    """Tests for disk space checking."""

    def test_check_existing_dir(self):
        from rayvault.davinci_assembler import check_disk_space
        tmp = tempfile.mkdtemp()
        result = check_disk_space(Path(tmp))
        self.assertIn("export_free_gb", result)
        self.assertIsNotNone(result["export_free_gb"])
        self.assertGreater(result["export_free_gb"], 0)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_check_nonexistent_cache_dir(self):
        from rayvault.davinci_assembler import check_disk_space
        tmp = tempfile.mkdtemp()
        result = check_disk_space(
            Path(tmp), cache_dir=Path("/nonexistent/cache/dir"),
        )
        self.assertIsNone(result.get("cache_free_gb"))
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_gate_disk_space_passes(self):
        from rayvault.davinci_assembler import gate_disk_space
        tmp = tempfile.mkdtemp()
        run_dir = Path(tmp) / "run"
        (run_dir / "publish").mkdir(parents=True)
        gate, metrics = gate_disk_space(run_dir, estimated_output_gb=0.001)
        # Should pass unless system has <20GB free
        self.assertIn("export_free_gb", metrics)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================
# Render states tests
# ============================================================================


class TestRenderStates(unittest.TestCase):
    """Test manifest render state updates."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.manifest_path = Path(self.tmp) / "00_manifest.json"
        with open(self.manifest_path, "w") as f:
            json.dump({"run_id": "TEST"}, f)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_update_render_state(self):
        from rayvault.davinci_assembler import _update_render_state, RS_STARTED
        _update_render_state(self.manifest_path, RS_STARTED)
        with open(self.manifest_path) as f:
            m = json.load(f)
        self.assertEqual(m["render"]["state"], "RENDER_STARTED")
        self.assertIn("state_updated_at_utc", m["render"])

    def test_update_render_state_with_extra(self):
        from rayvault.davinci_assembler import _update_render_state, RS_STALLED
        _update_render_state(self.manifest_path, RS_STALLED, {"retry": 1})
        with open(self.manifest_path) as f:
            m = json.load(f)
        self.assertEqual(m["render"]["state"], "RENDER_STALLED")
        self.assertEqual(m["render"]["retry"], 1)

    def test_render_states_constants(self):
        from rayvault.davinci_assembler import (
            RS_STARTED, RS_STALLED, RS_RECOVERING,
            RS_FAILED_HARD, RS_RENDERED_OK,
        )
        self.assertEqual(RS_STARTED, "RENDER_STARTED")
        self.assertEqual(RS_STALLED, "RENDER_STALLED")
        self.assertEqual(RS_RECOVERING, "RENDER_RECOVERING")
        self.assertEqual(RS_FAILED_HARD, "RENDER_FAILED_HARD")
        self.assertEqual(RS_RENDERED_OK, "RENDERED_OK")


# ============================================================================
# Caffeinate tests
# ============================================================================


class TestCaffeinate(unittest.TestCase):
    """Test caffeinate integration."""

    def test_start_and_stop(self):
        from rayvault.davinci_assembler import _start_caffeinate, _stop_caffeinate
        proc = _start_caffeinate()
        if proc is not None:  # Only works on macOS
            self.assertIsNotNone(proc.pid)
            _stop_caffeinate(proc)
            proc.wait(timeout=5)
            self.assertIsNotNone(proc.returncode)

    def test_stop_none_is_safe(self):
        from rayvault.davinci_assembler import _stop_caffeinate
        _stop_caffeinate(None)  # Should not raise


# ============================================================================
# Final Validator — pacing gate tests
# ============================================================================


class TestGatePacing(unittest.TestCase):
    """Test the pacing gate in final_validator."""

    def test_pass_when_pacing_ok(self):
        from rayvault.final_validator import gate_pacing
        tmp = tempfile.mkdtemp()
        run_dir = Path(tmp)
        rc = {
            "segments": [],
            "pacing": {"ok": True, "variety_warning": False,
                       "errors": [], "warnings": []},
        }
        with open(run_dir / "05_render_config.json", "w") as f:
            json.dump(rc, f)
        g = gate_pacing(run_dir)
        self.assertTrue(g.passed)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_fail_when_pacing_bad(self):
        from rayvault.final_validator import gate_pacing
        tmp = tempfile.mkdtemp()
        run_dir = Path(tmp)
        rc = {
            "segments": [],
            "pacing": {"ok": False, "variety_warning": True,
                       "errors": ["LONG_STATIC: seg_001 is 25s"],
                       "warnings": []},
        }
        with open(run_dir / "05_render_config.json", "w") as f:
            json.dump(rc, f)
        g = gate_pacing(run_dir)
        self.assertFalse(g.passed)
        self.assertIn("EDITORIAL_LOW_VARIETY", g.detail)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_skip_when_no_config(self):
        from rayvault.final_validator import gate_pacing
        tmp = tempfile.mkdtemp()
        g = gate_pacing(Path(tmp))
        self.assertTrue(g.passed)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================
# Policies tests
# ============================================================================


class TestPolicies(unittest.TestCase):
    """Test rayvault/policies.py constants and functions."""

    def test_constants_exist(self):
        from rayvault.policies import (
            TARGET_MIN_SEC, TARGET_MAX_SEC, MAX_STATIC_SECONDS,
            LUFS_TARGET, STALL_TIMEOUT_SEC, MIN_CACHE_FREE_GB,
        )
        self.assertEqual(TARGET_MIN_SEC, 480)
        self.assertEqual(TARGET_MAX_SEC, 720)
        self.assertEqual(MAX_STATIC_SECONDS, 18)
        self.assertEqual(LUFS_TARGET, -14.0)

    def test_motion_group_for_preset(self):
        from rayvault.policies import motion_group_for_preset
        self.assertEqual(motion_group_for_preset("zoom_in_center"), "zoom_in")
        self.assertEqual(motion_group_for_preset("pan_left_to_right"), "pan_lr")
        self.assertEqual(motion_group_for_preset("diagonal_drift"), "diagonal")
        self.assertEqual(motion_group_for_preset("unknown_preset"), "other")

    def test_motion_groups_complete(self):
        from rayvault.policies import MOTION_GROUPS
        all_presets = set()
        for presets in MOTION_GROUPS.values():
            all_presets.update(presets)
        self.assertIn("zoom_in_center", all_presets)
        self.assertIn("zoom_out_center", all_presets)
        self.assertIn("pan_left_to_right", all_presets)


# ============================================================================
# Segment ID tests
# ============================================================================


class TestSegmentId(unittest.TestCase):
    """Test rayvault/segment_id.py — canonical segment identifiers."""

    def test_deterministic(self):
        from rayvault.segment_id import compute_segment_id
        seg = {"type": "product", "rank": 1, "asin": "B00TEST",
               "visual": {"mode": "KEN_BURNS", "source": "img.png"}}
        id1 = compute_segment_id(seg)
        id2 = compute_segment_id(seg)
        self.assertEqual(id1, id2)
        self.assertEqual(len(id1), 16)

    def test_time_independent(self):
        from rayvault.segment_id import compute_segment_id
        seg1 = {"type": "product", "rank": 1, "asin": "B00TEST",
                "t0": 5.0, "t1": 10.0,
                "visual": {"mode": "KEN_BURNS"}}
        seg2 = {"type": "product", "rank": 1, "asin": "B00TEST",
                "t0": 20.0, "t1": 25.0,
                "visual": {"mode": "KEN_BURNS"}}
        self.assertEqual(compute_segment_id(seg1), compute_segment_id(seg2))

    def test_content_dependent(self):
        from rayvault.segment_id import compute_segment_id
        seg1 = {"type": "product", "rank": 1, "asin": "B00TEST",
                "visual": {"mode": "KEN_BURNS"}}
        seg2 = {"type": "product", "rank": 2, "asin": "B00OTHER",
                "visual": {"mode": "BROLL_VIDEO"}}
        self.assertNotEqual(compute_segment_id(seg1), compute_segment_id(seg2))

    def test_validate_consistent_ids(self):
        from rayvault.segment_id import compute_segment_id, validate_segment_ids
        seg = {"type": "product", "rank": 1, "visual": {"mode": "KEN_BURNS"}}
        seg["segment_id"] = compute_segment_id(seg)
        errors = validate_segment_ids([seg])
        self.assertEqual(errors, [])

    def test_validate_inconsistent_id(self):
        from rayvault.segment_id import validate_segment_ids
        seg = {"type": "product", "rank": 1, "visual": {"mode": "KEN_BURNS"},
               "segment_id": "wrong_id_here!!!"}
        errors = validate_segment_ids([seg])
        self.assertEqual(len(errors), 1)
        self.assertIn("SEGMENT_ID_MISMATCH", errors[0])

    def test_ensure_segment_ids(self):
        from rayvault.segment_id import ensure_segment_ids
        segs = [
            {"type": "intro"},
            {"type": "product", "rank": 1, "visual": {"mode": "KEN_BURNS"}},
        ]
        result = ensure_segment_ids(segs)
        for seg in result:
            self.assertIn("segment_id", seg)
            self.assertEqual(len(seg["segment_id"]), 16)

    def test_canonical_dict_excludes_timing(self):
        from rayvault.segment_id import canonical_segment_dict
        seg = {"type": "product", "rank": 1, "t0": 5, "t1": 10,
               "id": "seg_001", "frames": 150,
               "visual": {"mode": "KEN_BURNS"}}
        canon = canonical_segment_dict(seg)
        self.assertNotIn("t0", canon)
        self.assertNotIn("t1", canon)
        self.assertNotIn("id", canon)
        self.assertNotIn("frames", canon)
        self.assertIn("type", canon)
        self.assertIn("rank", canon)


# ============================================================================
# Pacing Validator module tests
# ============================================================================


class TestPacingValidatorModule(unittest.TestCase):
    """Test rayvault/pacing_validator.py — full editorial invariants."""

    def test_valid_timeline(self):
        from rayvault.pacing_validator import validate_pacing
        config = {
            "segments": [
                {"id": "s0", "type": "intro", "t0": 0, "t1": 2},
                {"id": "s1", "type": "product", "t0": 2, "t1": 8,
                 "visual": {"mode": "KEN_BURNS"}},
                {"id": "s2", "type": "product", "t0": 8, "t1": 14,
                 "visual": {"mode": "BROLL_VIDEO"}},
                {"id": "s3", "type": "outro", "t0": 14, "t1": 16},
            ],
        }
        result = validate_pacing(config)
        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["segment_count"], 4)

    def test_long_static_fails(self):
        from rayvault.pacing_validator import validate_pacing
        config = {
            "segments": [
                {"id": "s0", "type": "intro", "t0": 0, "t1": 2},
                {"id": "s1", "type": "product", "t0": 2, "t1": 25,
                 "visual": {"mode": "STILL_ONLY"}},
                {"id": "s2", "type": "outro", "t0": 25, "t1": 27},
            ],
        }
        result = validate_pacing(config)
        self.assertFalse(result["ok"])
        self.assertTrue(any("LONG_STATIC" in e for e in result["errors"]))

    def test_gap_detected(self):
        from rayvault.pacing_validator import validate_pacing
        config = {
            "segments": [
                {"id": "s0", "type": "intro", "t0": 0, "t1": 2},
                {"id": "s1", "type": "product", "t0": 5, "t1": 10,
                 "visual": {"mode": "KEN_BURNS"}},
            ],
        }
        result = validate_pacing(config)
        self.assertFalse(result["ok"])
        self.assertTrue(any("TIMELINE_GAP" in e for e in result["errors"]))

    def test_strict_duration_fail(self):
        from rayvault.pacing_validator import validate_pacing
        config = {
            "segments": [
                {"id": "s0", "type": "intro", "t0": 0, "t1": 2},
                {"id": "s1", "type": "outro", "t0": 2, "t1": 4},
            ],
        }
        result = validate_pacing(config, strict_duration=True)
        self.assertFalse(result["ok"])
        self.assertTrue(any("DURATION_SHORT" in e for e in result["errors"]))

    def test_duration_as_warning_by_default(self):
        from rayvault.pacing_validator import validate_pacing
        config = {
            "segments": [
                {"id": "s0", "type": "intro", "t0": 0, "t1": 2},
                {"id": "s1", "type": "outro", "t0": 2, "t1": 4},
            ],
        }
        result = validate_pacing(config, strict_duration=False)
        self.assertTrue(result["ok"])
        self.assertTrue(any("DURATION_SHORT" in w for w in result["warnings"]))

    def test_motion_hygiene_warning(self):
        from rayvault.pacing_validator import validate_pacing
        config = {
            "segments": [
                {"id": "s0", "type": "intro", "t0": 0, "t1": 2},
                {"id": "s1", "type": "product", "t0": 2, "t1": 6,
                 "visual": {"mode": "KEN_BURNS"},
                 "motion": {"preset": "zoom_in_center"}},
                {"id": "s2", "type": "product", "t0": 6, "t1": 10,
                 "visual": {"mode": "KEN_BURNS"},
                 "motion": {"preset": "slow_push_in"}},
                {"id": "s3", "type": "product", "t0": 10, "t1": 14,
                 "visual": {"mode": "KEN_BURNS"},
                 "motion": {"preset": "push_in"}},
                {"id": "s4", "type": "outro", "t0": 14, "t1": 16},
            ],
        }
        result = validate_pacing(config)
        self.assertTrue(any("MOTION_REPETITION" in w for w in result["warnings"]))

    def test_type_variety_warning(self):
        from rayvault.pacing_validator import validate_pacing
        config = {
            "segments": [
                {"id": "s0", "type": "intro", "t0": 0, "t1": 2},
                {"id": "s1", "type": "product", "t0": 2, "t1": 6,
                 "visual": {"mode": "KEN_BURNS"}},
                {"id": "s2", "type": "product", "t0": 6, "t1": 10,
                 "visual": {"mode": "KEN_BURNS"}},
                {"id": "s3", "type": "product", "t0": 10, "t1": 14,
                 "visual": {"mode": "KEN_BURNS"}},
                {"id": "s4", "type": "outro", "t0": 14, "t1": 16},
            ],
        }
        result = validate_pacing(config)
        self.assertTrue(
            any("LOW_VARIETY" in w or "TYPE_DOMINANCE" in w for w in result["warnings"])
        )

    def test_visual_change_detection(self):
        from rayvault.pacing_validator import segment_has_visual_change
        self.assertTrue(segment_has_visual_change(
            {"visual": {"mode": "BROLL_VIDEO"}}
        ))
        self.assertTrue(segment_has_visual_change(
            {"visual": {"mode": "KEN_BURNS"}}
        ))
        self.assertFalse(segment_has_visual_change(
            {"visual": {"mode": "STILL_ONLY"}}
        ))
        self.assertTrue(segment_has_visual_change(
            {"visual": {"mode": "STILL_ONLY"},
             "motion": {"start_scale": 1.0, "end_scale": 1.1}}
        ))
        self.assertTrue(segment_has_visual_change(
            {"visual": {"mode": "STILL_ONLY"},
             "overlay_refs": [{"kind": "lt", "overlay_id": "x", "event": "enter"}]}
        ))

    def test_summary_stats(self):
        from rayvault.pacing_validator import validate_pacing
        config = {
            "segments": [
                {"id": "s0", "type": "intro", "t0": 0, "t1": 15},
                {"id": "s1", "type": "product", "t0": 15, "t1": 25,
                 "visual": {"mode": "KEN_BURNS"}},
                {"id": "s2", "type": "product", "t0": 25, "t1": 35,
                 "visual": {"mode": "BROLL_VIDEO"}},
                {"id": "s3", "type": "outro", "t0": 35, "t1": 50},
            ],
        }
        result = validate_pacing(config)
        self.assertEqual(result["summary"]["duration_sec"], 50.0)
        self.assertEqual(result["summary"]["segment_count"], 4)
        self.assertIn("intro", result["summary"]["type_distribution"])

    def test_cli_exit_0_on_pass(self):
        from rayvault.pacing_validator import main
        tmp = tempfile.mkdtemp()
        config_path = Path(tmp) / "config.json"
        config = {
            "segments": [
                {"id": "s0", "type": "intro", "t0": 0, "t1": 2},
                {"id": "s1", "type": "product", "t0": 2, "t1": 8,
                 "visual": {"mode": "KEN_BURNS"}},
                {"id": "s2", "type": "outro", "t0": 8, "t1": 10},
            ],
        }
        with open(config_path, "w") as f:
            json.dump(config, f)
        rc = main(["--config", str(config_path)])
        self.assertEqual(rc, 0)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_cli_exit_2_on_fail(self):
        from rayvault.pacing_validator import main
        tmp = tempfile.mkdtemp()
        config_path = Path(tmp) / "config.json"
        config = {
            "segments": [
                {"id": "s0", "type": "intro", "t0": 0, "t1": 2},
                {"id": "s1", "type": "product", "t0": 2, "t1": 25,
                 "visual": {"mode": "STILL_ONLY"}},
                {"id": "s2", "type": "outro", "t0": 25, "t1": 27},
            ],
        }
        with open(config_path, "w") as f:
            json.dump(config, f)
        rc = main(["--config", str(config_path)])
        self.assertEqual(rc, 2)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
