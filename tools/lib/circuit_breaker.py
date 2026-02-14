"""Circuit Breaker — gates pipeline on evidence confidence (RayviewsLab calibration).

Simple, debuggable, linear scoring. No complex MPC formulas.

Three tiers, aligned with what actually destroys credibility for 30+ audience:

    Tier A (CRITICAL — gates run):
        price, voltage, compatibility, core_specs
    Tier B (IMPORTANT — logs alert, continues):
        availability, shipping, promo_badge, review_sentiment
    Tier C (INFORMATIVE — never blocks):
        material, color, box_contents, warranty

Rule: only Tier A claims can trip the circuit breaker.
Score per claim = best confidence from evidence items (0.0-1.0).
Gate threshold: any Tier A claim below 0.6 → pause run.

Token optimization built-in:
    - Price: always refresh (TTL 12h)
    - Specs: refresh only if hash changed or TTL > 120d
    - Reviews: refresh only if new product or TTL > 30d

Stdlib only.

Usage:
    from lib.circuit_breaker import evaluate_evidence, CBResult

    result = evaluate_evidence(evidence_items)
    if result.should_gate:
        print(result.gate_reason)
    elif result.alerts:
        for a in result.alerts:
            print(f"ALERT: {a}")
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Tier configuration — calibrated for RayviewsLab
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Price mode: determines whether price gates (Tier A) or hedges (Tier B).
#
#   "exact"  — script asserts exact price ("está R$ 1.199")  → Tier A, gates run
#   "range"  — script uses range + link ("confira no link")  → Tier B, hedge + timestamp
#
# Change this one value to switch pipeline behavior for price.
# ---------------------------------------------------------------------------
PRICE_MODE: str = "exact"  # "exact" | "range"

# Tier A: CRITICAL — destroys credibility if wrong. Gates run.
_TIER_A_BASE: dict[str, dict] = {
    "voltage":       {"weight": 1.0, "ttl_hours": 4320.0},   # 180 days
    "compatibility": {"weight": 1.0, "ttl_hours": 2880.0},   # 120 days
    "core_specs":    {"weight": 0.9, "ttl_hours": 2880.0},   # 120 days
}
_PRICE_CONFIG = {"weight": 1.0, "ttl_hours": 12.0}

# Build TIER_A dynamically based on PRICE_MODE
TIER_A: dict[str, dict] = {**_TIER_A_BASE}
if PRICE_MODE == "exact":
    TIER_A["price"] = _PRICE_CONFIG

# Tier B: IMPORTANT — affects conversion but not structural. Alert only.
TIER_B: dict[str, dict] = {
    "availability":     {"weight": 0.5, "ttl_hours": 12.0},
    "shipping":         {"weight": 0.4, "ttl_hours": 168.0},   # 7 days
    "promo_badge":      {"weight": 0.6, "ttl_hours": 6.0},
    "review_sentiment": {"weight": 0.6, "ttl_hours": 720.0},   # 30 days
}
if PRICE_MODE == "range":
    TIER_B["price"] = _PRICE_CONFIG

# Tier C: INFORMATIVE — never blocks.
TIER_C: dict[str, dict] = {
    "material":     {"weight": 0.3, "ttl_hours": 8760.0},  # 365 days
    "color":        {"weight": 0.2, "ttl_hours": 8760.0},
    "box_contents": {"weight": 0.3, "ttl_hours": 8760.0},
    "warranty":     {"weight": 0.5, "ttl_hours": 4320.0},  # 180 days
}

# Merged lookup
ALL_CLAIMS: dict[str, dict] = {**TIER_A, **TIER_B, **TIER_C}

# Default gate threshold (Tier A claims below this → pause)
DEFAULT_THRESHOLD = 0.6


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvidenceItem:
    """A single piece of evidence supporting a claim."""
    claim_type: str
    confidence: float       # 0.0 to 1.0
    source_url: str = ""
    source_name: str = ""
    fetched_at: str = ""    # ISO timestamp
    trust_tier: int = 3     # 1=low, 2=medium, 3=high, 4=authoritative
    value: Any = None       # The actual claim value (price, bool, etc.)
    claim_id: str = ""

    @property
    def age_hours(self) -> float:
        """Hours since fetched. Returns inf if unknown."""
        if not self.fetched_at:
            return float("inf")
        try:
            from datetime import datetime, timezone
            ts = datetime.fromisoformat(self.fetched_at).timestamp()
            return (time.time() - ts) / 3600
        except (ValueError, OSError):
            return float("inf")

    def is_expired(self, ttl_hours: float | None = None) -> bool:
        """True if evidence is older than its claim type's TTL."""
        if ttl_hours is None:
            cfg = ALL_CLAIMS.get(self.claim_type, {})
            ttl_hours = cfg.get("ttl_hours", 48.0)
        return self.age_hours > ttl_hours


@dataclass
class ClaimScore:
    """Score for a single claim type."""
    claim_type: str
    tier: str               # "A", "B", "C"
    score: float            # Best confidence (0.0 to 1.0)
    weight: float
    is_weak: bool           # Below threshold
    evidence_count: int
    weakness_reason: str = ""   # "expired" | "missing" | "low_trust" | "low_confidence"
    can_auto_refetch: bool = False


@dataclass
class CBResult:
    """Circuit breaker evaluation result."""
    should_gate: bool           # True = pause run (only Tier A can cause this)
    gate_reason: str = ""
    scores: list[ClaimScore] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)  # Tier B warnings
    can_auto_refetch: bool = False
    threshold: float = DEFAULT_THRESHOLD

    @property
    def summary(self) -> str:
        """One-line summary for logging."""
        status = "GATE" if self.should_gate else "PASS"
        weak = [s.claim_type for s in self.scores if s.is_weak and s.tier == "A"]
        alerts = len(self.alerts)
        parts = [f"CB {status} (threshold={self.threshold:.1f})"]
        if weak:
            parts.append(f"weak_critical=[{', '.join(weak)}]")
        if alerts:
            parts.append(f"alerts={alerts}")
        return " ".join(parts)

    def to_snapshot(self) -> dict:
        """Serialize for context_snapshot storage."""
        return {
            "should_gate": self.should_gate,
            "threshold": self.threshold,
            "gate_reason": self.gate_reason,
            "can_auto_refetch": self.can_auto_refetch,
            "alert_count": len(self.alerts),
            "scores": [
                {
                    "claim_type": s.claim_type,
                    "tier": s.tier,
                    "score": round(s.score, 3),
                    "is_weak": s.is_weak,
                    "evidence_count": s.evidence_count,
                    "weakness_reason": s.weakness_reason,
                }
                for s in self.scores
            ],
            "hedge_annotations": build_hedge_annotations(self),
        }


# ---------------------------------------------------------------------------
# Core evaluation — simple and linear
# ---------------------------------------------------------------------------

def _get_tier(claim_type: str) -> str:
    """Return tier letter for a claim type."""
    if claim_type in TIER_A:
        return "A"
    if claim_type in TIER_B:
        return "B"
    if claim_type in TIER_C:
        return "C"
    return "C"  # unknown claims default to informative


def _score_claim(
    claim_type: str,
    items: list[EvidenceItem],
    threshold: float,
) -> ClaimScore:
    """Score a single claim: best confidence from available evidence."""
    tier = _get_tier(claim_type)
    cfg = ALL_CLAIMS.get(claim_type, {"weight": 0.3, "ttl_hours": 48.0})
    weight = cfg["weight"]
    ttl = cfg["ttl_hours"]

    if not items:
        return ClaimScore(
            claim_type=claim_type,
            tier=tier,
            score=0.0,
            weight=weight,
            is_weak=True,
            evidence_count=0,
            weakness_reason="missing",
            can_auto_refetch=True,
        )

    # Best confidence from non-expired, non-low-trust items
    fresh = [e for e in items if not e.is_expired(ttl)]
    trustworthy = [e for e in fresh if e.trust_tier >= 3]

    if trustworthy:
        best = max(e.confidence for e in trustworthy)
    elif fresh:
        best = max(e.confidence for e in fresh)
    else:
        # All expired — always weak for Tier A (price might have changed)
        best = max(e.confidence for e in items)
        all_low_trust = all(e.trust_tier <= 2 for e in items)
        return ClaimScore(
            claim_type=claim_type,
            tier=tier,
            score=round(best, 4),
            weight=weight,
            is_weak=True,  # expired = always weak, regardless of old confidence
            evidence_count=len(items),
            weakness_reason="expired",
            can_auto_refetch=not all_low_trust,
        )

    is_weak = best < threshold
    weakness_reason = ""
    can_auto_refetch = False

    if is_weak:
        if not trustworthy and fresh:
            weakness_reason = "low_trust"
            can_auto_refetch = False
        else:
            weakness_reason = "low_confidence"
            can_auto_refetch = True

    return ClaimScore(
        claim_type=claim_type,
        tier=tier,
        score=round(best, 4),
        weight=weight,
        is_weak=is_weak,
        evidence_count=len(items),
        weakness_reason=weakness_reason,
        can_auto_refetch=can_auto_refetch,
    )


def evaluate_evidence(
    evidence: list[EvidenceItem] | list[dict],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> CBResult:
    """Evaluate evidence and decide whether to gate the pipeline.

    Simple rule: any Tier A claim below threshold → gate.
    Tier B below threshold → alert (no gate).
    Tier C → ignored.

    Args:
        evidence: List of EvidenceItem or dicts with same fields.
        threshold: Score below which a claim is "weak" (default 0.6).

    Returns:
        CBResult with gate decision, per-claim scores, and alerts.
    """
    # Normalize dicts
    items: list[EvidenceItem] = []
    for e in evidence:
        if isinstance(e, dict):
            items.append(EvidenceItem(
                claim_type=e.get("claim_type", ""),
                confidence=float(e.get("confidence", 0)),
                source_url=e.get("source_url", ""),
                source_name=e.get("source_name", ""),
                fetched_at=e.get("fetched_at", ""),
                trust_tier=int(e.get("trust_tier", 3)),
                value=e.get("value"),
                claim_id=e.get("claim_id", ""),
            ))
        else:
            items.append(e)

    # Group by claim type
    by_type: dict[str, list[EvidenceItem]] = {}
    for item in items:
        if item.claim_type:
            by_type.setdefault(item.claim_type, []).append(item)

    # Evaluate all known claim types + any found in evidence
    all_types = set(by_type.keys()) | set(TIER_A.keys())

    scores: list[ClaimScore] = []
    alerts: list[str] = []
    gate_reasons: list[str] = []
    all_weak_refetchable = True

    for ct in sorted(all_types):
        claim_items = by_type.get(ct, [])
        score = _score_claim(ct, claim_items, threshold)
        scores.append(score)

        if score.is_weak:
            if score.tier == "A":
                gate_reasons.append(
                    f"{ct}: score={score.score:.2f} ({score.weakness_reason})"
                )
                if not score.can_auto_refetch:
                    all_weak_refetchable = False
            elif score.tier == "B":
                alerts.append(
                    f"{ct}: score={score.score:.2f} ({score.weakness_reason})"
                )

    should_gate = len(gate_reasons) > 0
    gate_reason = ""
    if should_gate:
        gate_reason = "Critical claims below threshold: " + "; ".join(gate_reasons)

    can_auto_refetch = should_gate and all_weak_refetchable

    return CBResult(
        should_gate=should_gate,
        gate_reason=gate_reason,
        scores=scores,
        alerts=alerts,
        can_auto_refetch=can_auto_refetch,
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Editorial hedging — when evidence is weak, script language must adapt
# ---------------------------------------------------------------------------

# Maps (weakness_reason, tier) → hedging template for script generation.
# Used after "ignore" approval or for Tier B/C weak claims that don't gate.
#
# SAFETY RULE: voltage, compatibility, core_specs are NEVER hedged.
# If weak, they gate the run. If someone "ignores" the gate, those claims
# are omitted from the script (not softened with qualifying language).
# Only price (and future hedgeable claims) get editorial hedging.

# Claims where weak evidence = omit from script, never hedge.
# These are safety-critical: wrong voltage/compatibility can cause real harm.
GATE_ONLY_CLAIMS: set[str] = {"voltage", "compatibility", "core_specs"}

HEDGE_TEMPLATES: dict[str, str] = {
    # Tier A weak — hedgeable claims only (price when in "exact" mode)
    "expired:A":        "No momento da gravacao, {claim} era {value}. Confere no link porque pode ter mudado.",
    "low_confidence:A": "Segundo as fontes disponiveis, {claim} indica {value} — vale confirmar na pagina oficial.",
    "low_trust:A":      "Encontramos indicacao de {claim}: {value}, mas a fonte nao e oficial. Verifica antes de comprar.",
    "missing:A":        "Nao conseguimos confirmar {claim} com fontes confiaveis. Confere direto no fabricante.",
    # Tier B weak (alert only, never gates)
    "expired:B":        "Na data da gravacao, {claim} era {value}.",
    "low_confidence:B": "{claim}: {value} (pode variar).",
    "missing:B":        "",  # omit from script entirely
    # Tier C — never hedged, just factual or omitted
    "expired:C":        "",
    "missing:C":        "",
}


def _build_support_line(
    claim_type: str,
    evidence_by_type: dict[str, list[EvidenceItem]],
) -> str:
    """Build a citation string from the best evidence for a claim.

    Example: "Fonte: manual do fabricante (PDF), verificado em 2026-02-14."
    """
    items = evidence_by_type.get(claim_type, [])
    if not items:
        return ""
    # Pick best by trust_tier, then confidence
    best = max(items, key=lambda e: (e.trust_tier, e.confidence))
    source = best.source_name or best.source_url or "desconhecida"
    date_str = ""
    if best.fetched_at:
        try:
            from datetime import datetime as _dt
            dt = _dt.fromisoformat(best.fetched_at)
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, OSError):
            pass
    if date_str:
        return f"Fonte: {source}, verificado em {date_str}."
    return f"Fonte: {source}."


def build_hedge_annotations(
    result: CBResult,
    evidence: list[EvidenceItem] | list[dict] | None = None,
) -> list[dict]:
    """Generate editorial hedging annotations from CB evaluation.

    Args:
        result: CBResult from evaluate_evidence().
        evidence: Optional original evidence list for support_line generation.
            If not provided, support_line will be empty.

    Returns list of:
        {claim_type, hedge_level, template, weakness_reason, score, support_line}

    hedge_level:
        "firm"        — strong evidence, use assertive language
        "hedged"      — weak evidence, use qualifying language (price, etc.)
        "gate_only"   — safety-critical claim is weak; omit from script, should have gated
        "omit"        — too weak to mention, skip in script

    SAFETY RULE: voltage, compatibility, core_specs are NEVER hedged.
    If weak after "ignore" approval, they become "gate_only" (omitted from script).
    """
    # Build evidence lookup for support_line
    evidence_by_type: dict[str, list[EvidenceItem]] = {}
    if evidence:
        for e in evidence:
            if isinstance(e, dict):
                item = EvidenceItem(
                    claim_type=e.get("claim_type", ""),
                    confidence=float(e.get("confidence", 0)),
                    source_url=e.get("source_url", ""),
                    source_name=e.get("source_name", ""),
                    fetched_at=e.get("fetched_at", ""),
                    trust_tier=int(e.get("trust_tier", 3)),
                    value=e.get("value"),
                )
            else:
                item = e
            if item.claim_type:
                evidence_by_type.setdefault(item.claim_type, []).append(item)

    annotations: list[dict] = []
    for s in result.scores:
        support = _build_support_line(s.claim_type, evidence_by_type)

        if not s.is_weak:
            annotations.append({
                "claim_type": s.claim_type,
                "hedge_level": "firm",
                "template": "",
                "weakness_reason": "",
                "score": round(s.score, 3),
                "support_line": support,
            })
            continue

        # Safety-critical claims: never hedge, always gate_only when weak
        if s.claim_type in GATE_ONLY_CLAIMS:
            annotations.append({
                "claim_type": s.claim_type,
                "hedge_level": "gate_only",
                "template": "",
                "weakness_reason": s.weakness_reason,
                "score": round(s.score, 3),
                "support_line": "",  # no citation for weak safety claims
            })
            continue

        key = f"{s.weakness_reason}:{s.tier}"
        template = HEDGE_TEMPLATES.get(key, "")

        if not template:
            hedge_level = "omit"
        else:
            hedge_level = "hedged"

        annotations.append({
            "claim_type": s.claim_type,
            "hedge_level": hedge_level,
            "template": template,
            "weakness_reason": s.weakness_reason,
            "score": round(s.score, 3),
            "support_line": support if hedge_level == "hedged" else "",
        })

    return annotations


# ---------------------------------------------------------------------------
# Refetch decision
# ---------------------------------------------------------------------------

def should_auto_refetch(
    result: CBResult,
    *,
    refetch_attempted: bool = False,
) -> bool:
    """Should the pipeline silently auto-refetch evidence?

    Rules:
    - Only once (refetch_attempted=True → False)
    - Only if all weaknesses are due to expiration/missing
    - Never if weakness is structurally low trust
    """
    if not result.should_gate:
        return False
    if refetch_attempted:
        return False
    return result.can_auto_refetch


# ---------------------------------------------------------------------------
# Token optimization helper
# ---------------------------------------------------------------------------

def needs_refresh(
    claim_type: str,
    *,
    last_fetched_at: str = "",
    content_hash_changed: bool = False,
    fingerprint_changed: bool = False,
    is_new_product: bool = False,
) -> bool:
    """Decide if a claim type needs re-fetching (token-aware).

    Optimization rules:
    - price: always refresh (TTL 12h)
    - core_specs/voltage/compatibility: refresh if fingerprint/hash changed or TTL expired
    - review_sentiment: only if new product or TTL expired
    - Tier C: almost never refresh
    - fingerprint_changed: SKU variant changed → force refresh for specs claims
    """
    cfg = ALL_CLAIMS.get(claim_type, {"ttl_hours": 48.0})
    ttl = cfg["ttl_hours"]

    # SKU fingerprint changed → force refresh for structural claims
    if fingerprint_changed and claim_type in ("core_specs", "voltage", "compatibility"):
        return True

    # Check age
    age_hours = float("inf")
    if last_fetched_at:
        try:
            from datetime import datetime, timezone
            ts = datetime.fromisoformat(last_fetched_at).timestamp()
            age_hours = (time.time() - ts) / 3600
        except (ValueError, OSError):
            pass

    # Price: always refresh if expired
    if claim_type == "price":
        return age_hours > ttl

    # Specs/voltage/compatibility: refresh if hash changed OR TTL expired
    if claim_type in ("core_specs", "voltage", "compatibility"):
        if content_hash_changed:
            return True
        return age_hours > ttl

    # Reviews: refresh if new product OR TTL expired
    if claim_type == "review_sentiment":
        if is_new_product:
            return True
        return age_hours > ttl

    # Everything else: standard TTL check
    return age_hours > ttl


# ---------------------------------------------------------------------------
# Conflict detection — high-trust sources disagreeing
# ---------------------------------------------------------------------------

def detect_conflicts(
    evidence: list[EvidenceItem] | list[dict],
    *,
    min_trust_tier: int = 4,
) -> list[dict]:
    """Detect conflicts where high-trust sources disagree on the same claim.

    Returns list of conflict dicts:
        {claim_type, values: [{value, source, trust_tier}], severity}

    A conflict on voltage/compatibility/core_specs is "critical".
    """
    # Normalize
    items: list[EvidenceItem] = []
    for e in evidence:
        if isinstance(e, dict):
            items.append(EvidenceItem(
                claim_type=e.get("claim_type", ""),
                confidence=float(e.get("confidence", 0)),
                source_url=e.get("source_url", ""),
                source_name=e.get("source_name", ""),
                trust_tier=int(e.get("trust_tier", 3)),
                value=e.get("value"),
            ))
        else:
            items.append(e)

    # Group high-trust items by claim type
    by_type: dict[str, list[EvidenceItem]] = {}
    for item in items:
        if item.trust_tier >= min_trust_tier and item.value is not None:
            by_type.setdefault(item.claim_type, []).append(item)

    conflicts: list[dict] = []
    for ct, claim_items in by_type.items():
        # Get unique values (stringify for comparison)
        value_groups: dict[str, list[EvidenceItem]] = {}
        for item in claim_items:
            key = str(item.value).strip().lower()
            value_groups.setdefault(key, []).append(item)

        if len(value_groups) > 1:
            # Conflict detected
            severity = "critical" if ct in TIER_A else "warning"
            values = []
            for val_key, group in value_groups.items():
                best = max(group, key=lambda e: e.trust_tier)
                values.append({
                    "value": best.value,
                    "source": best.source_name or best.source_url,
                    "trust_tier": best.trust_tier,
                })

            conflicts.append({
                "claim_type": ct,
                "values": values,
                "severity": severity,
            })

    return conflicts


# ---------------------------------------------------------------------------
# SKU fingerprint
# ---------------------------------------------------------------------------

def compute_fingerprint(
    asin: str,
    *,
    brand: str = "",
    model_number: str = "",
    ean_upc: str = "",
    variant_attrs: dict | None = None,
    title: str = "",
) -> str:
    """Compute a deterministic fingerprint hash for a product SKU.

    If any of model_number, ean_upc, or variant_attrs change,
    the fingerprint changes → triggering evidence invalidation.
    """
    import hashlib
    parts = [
        asin.strip(),
        brand.strip().lower(),
        model_number.strip().lower(),
        ean_upc.strip(),
        json.dumps(variant_attrs or {}, sort_keys=True),
        title.strip().lower()[:100],
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# Need json for compute_fingerprint
import json
