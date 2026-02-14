"""Schema definitions for LLM contracts — Amazon extractor + Ranker.

Single source of truth for output schemas used by ContractSpec.
Each schema is JSON Schema draft-07 compatible (simple subset).

Stdlib only — no external deps.

Usage:
    from tools.lib.schemas import AMAZON_EXTRACT_SCHEMA, RANKER_SCHEMA
    from tools.lib.schemas import AMAZON_EXTRACT_CONTRACT, RANKER_CONTRACT
"""

from __future__ import annotations

from tools.lib.prompt_contract_loader import (
    ContractSpec, CachePolicy, CACHE_POLICIES, DEFAULT_ECONOMY_RULES,
)


# ---------------------------------------------------------------------------
# Amazon ASIN Extractor schema (output)
# ---------------------------------------------------------------------------

AMAZON_EXTRACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "asin", "facts", "signals", "issues"],
    "properties": {
        "status": {"type": "string", "enum": ["ok", "needs_human"]},
        "asin": {"type": "string", "minLength": 8, "maxLength": 16},

        "facts": {
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "price", "rating", "reviews", "availability", "brand", "top_features"],
            "properties": {
                "title": {"type": "string", "minLength": 3, "maxLength": 220},
                "price": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["amount", "currency"],
                    "properties": {
                        "amount": {"type": "number"},
                        "currency": {"type": "string", "minLength": 3, "maxLength": 3},
                    },
                },
                "rating": {"type": "number"},
                "reviews": {"type": "integer"},
                "availability": {"type": "string", "maxLength": 80},
                "brand": {"type": "string", "maxLength": 60},
                "top_features": {
                    "type": "array",
                    "minItems": 0,
                    "maxItems": 10,
                    "items": {"type": "string", "maxLength": 90},
                },
            },
        },

        "signals": {
            "type": "object",
            "additionalProperties": False,
            "required": ["confidence", "needs_refetch", "suspected_layout_change"],
            "properties": {
                "confidence": {"type": "number"},
                "needs_refetch": {"type": "boolean"},
                "suspected_layout_change": {"type": "boolean"},
            },
        },

        "issues": {
            "type": "array",
            "minItems": 0,
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["code", "msg"],
                "properties": {
                    "code": {
                        "type": "string",
                        "enum": [
                            "missing_price",
                            "missing_title",
                            "price_parse_failed",
                            "rating_parse_failed",
                            "reviews_parse_failed",
                            "conflicting_signals",
                            "html_noise_detected",
                            "amazon_layout_change",
                        ],
                    },
                    "msg": {"type": "string", "maxLength": 160},
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Ranker Top-3 schema (output)
# ---------------------------------------------------------------------------

RANKER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "winners", "rejected", "notes"],
    "properties": {
        "status": {"type": "string", "enum": ["ok", "needs_human"]},

        "winners": {
            "type": "array",
            "minItems": 0,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["asin", "slot", "score", "why"],
                "properties": {
                    "asin": {"type": "string", "minLength": 8, "maxLength": 16},
                    "slot": {
                        "type": "string",
                        "enum": ["best_overall", "best_value", "best_premium"],
                    },
                    "score": {"type": "number"},
                    "why": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 4,
                        "items": {"type": "string", "maxLength": 90},
                    },
                },
            },
        },

        "rejected": {
            "type": "array",
            "minItems": 0,
            "maxItems": 40,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["asin", "reason_code"],
                "properties": {
                    "asin": {"type": "string", "minLength": 8, "maxLength": 16},
                    "reason_code": {
                        "type": "string",
                        "enum": [
                            "price_out_of_budget",
                            "rating_too_low",
                            "too_few_reviews",
                            "missing_critical_fields",
                            "brand_excluded",
                            "needs_human_upstream",
                            "duplicate_pick",
                            "low_confidence",
                        ],
                    },
                },
            },
        },

        "notes": {
            "type": "object",
            "additionalProperties": False,
            "required": ["decision_trace"],
            "properties": {
                "decision_trace": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 8,
                    "items": {"type": "string", "maxLength": 120},
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Pre-built ContractSpec instances
# ---------------------------------------------------------------------------

AMAZON_EXTRACT_CONTRACT = ContractSpec(
    name="amazon_asin_extractor",
    version="v0.1.0",
    cache_policy=CACHE_POLICIES["6h"],
    schema=AMAZON_EXTRACT_SCHEMA,
    economy_rules=[
        *DEFAULT_ECONOMY_RULES,
        "Do not repeat input. Do not include raw fields.",
        "Top features must be short noun-phrases.",
        "If price is missing/ambiguous, set status=needs_human and add issues.",
        "If currency is unclear, set currency from constraints.currency_hint.",
        'If price_text contains "from"/"starting at", set status=needs_human + issue=conflicting_signals.',
        "Never invent missing facts.",
    ],
)

RANKER_CONTRACT = ContractSpec(
    name="ranker_top3",
    version="v0.1.0",
    cache_policy=CACHE_POLICIES["6h"],
    schema=RANKER_SCHEMA,
    economy_rules=[
        *DEFAULT_ECONOMY_RULES,
        "Apply HARD rules first, then SOFT scoring.",
        "Never pick the same ASIN twice.",
        "Provide why as short noun-phrases, not sentences.",
        "If fewer than 2 viable candidates, set status=needs_human.",
    ],
)


# ---------------------------------------------------------------------------
# Ranker prefilter — cheap Python filter before LLM call
# ---------------------------------------------------------------------------

def prefilter_candidates(
    candidates: list[dict],
    *,
    budget_min: float = 0,
    budget_max: float = float("inf"),
    budget_currency: str = "USD",
    min_rating: float = 0,
    min_reviews: int = 0,
    exclude_brands: list[str] | None = None,
    max_candidates: int = 10,
) -> tuple[list[dict], list[dict]]:
    """Pre-filter candidates in Python before sending to LLM ranker.

    Applies hard rules deterministically (no LLM needed):
    - Remove needs_human
    - Remove price out of budget
    - Remove rating below threshold
    - Remove reviews below threshold
    - Remove excluded brands
    - Keep top N by heuristic score

    Returns (passed, rejected) — both lists of candidate dicts.
    """
    exclude_set = {b.lower() for b in (exclude_brands or [])}
    passed = []
    rejected = []

    for c in candidates:
        # Skip needs_human
        if c.get("status") == "needs_human":
            rejected.append({"asin": c.get("asin", ""), "reason_code": "needs_human_upstream"})
            continue

        facts = c.get("facts", {})
        price = facts.get("price", {})
        amount = price.get("amount", 0)
        currency = price.get("currency", "")
        rating = facts.get("rating", 0)
        reviews = facts.get("reviews", 0)
        brand = facts.get("brand", "").lower()

        # Missing critical fields
        if not facts.get("title") or not amount or not currency:
            rejected.append({"asin": c.get("asin", ""), "reason_code": "missing_critical_fields"})
            continue

        # Budget check
        if currency.upper() == budget_currency.upper():
            if amount < budget_min or amount > budget_max:
                rejected.append({"asin": c.get("asin", ""), "reason_code": "price_out_of_budget"})
                continue

        # Rating check
        if rating < min_rating:
            rejected.append({"asin": c.get("asin", ""), "reason_code": "rating_too_low"})
            continue

        # Reviews check
        if reviews < min_reviews:
            rejected.append({"asin": c.get("asin", ""), "reason_code": "too_few_reviews"})
            continue

        # Brand exclusion
        if brand in exclude_set:
            rejected.append({"asin": c.get("asin", ""), "reason_code": "brand_excluded"})
            continue

        # Confidence check
        confidence = c.get("signals", {}).get("confidence", 1.0)
        if confidence < 0.3:
            rejected.append({"asin": c.get("asin", ""), "reason_code": "low_confidence"})
            continue

        passed.append(c)

    # Sort by heuristic score and keep top N
    import math

    def _heuristic(c: dict) -> float:
        facts = c.get("facts", {})
        r = facts.get("rating", 0)
        rev = facts.get("reviews", 0)
        conf = c.get("signals", {}).get("confidence", 1.0)
        return (r * 20) + (math.log10(max(rev, 1)) * 10) + (conf * 10)

    passed.sort(key=_heuristic, reverse=True)
    overflow = passed[max_candidates:]
    passed = passed[:max_candidates]

    return passed, rejected
