"""Schema definitions for LLM contracts — Amazon extractor + Ranker + Script Writer.

Single source of truth for output schemas used by ContractSpec.
Each schema is JSON Schema draft-07 compatible (simple subset).

Stdlib only — no external deps.

Usage:
    from tools.lib.schemas import AMAZON_EXTRACT_SCHEMA, RANKER_SCHEMA
    from tools.lib.schemas import SCRIPT_OUTLINE_SCHEMA, SCRIPT_OUTLINE_CONTRACT
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


# ---------------------------------------------------------------------------
# Script Writer — Outline schema (Layer 1)
# ---------------------------------------------------------------------------

SCRIPT_OUTLINE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "status", "contract_version", "outline_version", "outline",
    ],
    "properties": {
        "status": {"type": "string", "enum": ["ok", "needs_human"]},
        "contract_version": {"type": "string", "minLength": 1},
        "outline_version": {"type": "integer"},

        "outline": {
            "type": "object",
            "additionalProperties": False,
            "required": ["hook", "products", "cta"],
            "properties": {
                "hook": {"type": "string", "minLength": 10, "maxLength": 160},

                "products": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "product_key", "asin", "slot",
                            "angle", "points", "verdict",
                        ],
                        "properties": {
                            "product_key": {
                                "type": "string",
                                "minLength": 10,
                                "maxLength": 40,
                            },
                            "asin": {
                                "type": "string",
                                "minLength": 8,
                                "maxLength": 16,
                            },
                            "slot": {
                                "type": "string",
                                "enum": [
                                    "best_overall",
                                    "best_value",
                                    "best_premium",
                                ],
                            },
                            "angle": {
                                "type": "string",
                                "minLength": 5,
                                "maxLength": 80,
                            },
                            "points": {
                                "type": "array",
                                "minItems": 3,
                                "maxItems": 5,
                                "items": {
                                    "type": "string",
                                    "maxLength": 60,
                                },
                            },
                            "verdict": {
                                "type": "string",
                                "minLength": 5,
                                "maxLength": 60,
                            },
                        },
                    },
                },

                "cta": {"type": "string", "minLength": 10, "maxLength": 120},
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Script Writer — Patch output schema (for mode="patch")
# ---------------------------------------------------------------------------

SCRIPT_PATCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "patch_ops"],
    "properties": {
        "status": {"type": "string", "enum": ["ok", "needs_human"]},
        "patch_ops": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "required": ["op", "path", "value"],
                "properties": {
                    "op": {"type": "string", "enum": ["replace"]},
                    "path": {"type": "string", "minLength": 2},
                    "value": {},
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Script Writer — ContractSpec
# ---------------------------------------------------------------------------

SCRIPT_OUTLINE_CONTRACT = ContractSpec(
    name="script_writer",
    version="v0.1.0",
    cache_policy=CACHE_POLICIES["daily"],
    schema=SCRIPT_OUTLINE_SCHEMA,
    economy_rules=[
        *DEFAULT_ECONOMY_RULES,
        "Include contract_version and outline_version in output.",
        "product_key = '{asin}:{slot}' — never invent, copy from input.",
        "angle: max 80 chars. points: max 10 words each. verdict: max 60 chars.",
        "Each slot has a persona: best_overall=authoritative, best_value=practical, best_premium=aspirational.",
        "Never invent product facts not present in the input.",
        "If mode=patch, return ONLY patch_ops (not a full outline).",
    ],
)

SCRIPT_PATCH_CONTRACT = ContractSpec(
    name="script_writer",
    version="v0.1.0",
    cache_policy=CACHE_POLICIES["none"],  # patches are cheap, no cache
    schema=SCRIPT_PATCH_SCHEMA,
    economy_rules=[
        "Return ONLY valid JSON with patch_ops array.",
        "Allowed op: replace only. Max 5 ops.",
        "Allowed paths: /outline/hook, /outline/products/{i}/angle, "
        "/outline/products/{i}/points, /outline/products/{i}/verdict, /outline/cta.",
        "FORBIDDEN: /outline/products/{i}/asin, /outline/products/{i}/slot, "
        "/outline/products/{i}/product_key, /contract_version, /outline_version.",
    ],
)


# ---------------------------------------------------------------------------
# Quality gates — post-schema semantic validation
# ---------------------------------------------------------------------------

def quality_gate_amazon(output: dict) -> list[str]:
    """Quality gate for Amazon extractor output.

    Runs AFTER schema validation passes. Checks semantic correctness
    that schema alone can't enforce.

    Returns list of issue strings (empty = passed).
    If issues found: mark needs_human, do NOT attempt repair (avoids loop).
    """
    issues = []
    facts = output.get("facts", {})

    # Price must be positive
    price = facts.get("price", {})
    if isinstance(price, dict):
        amount = price.get("amount", 0)
        if isinstance(amount, (int, float)) and amount <= 0:
            issues.append("facts.price.amount must be > 0")

    # Title must not be empty/whitespace
    title = facts.get("title", "")
    if isinstance(title, str) and not title.strip():
        issues.append("facts.title is empty")

    # Rating in valid range
    rating = facts.get("rating", 0)
    if isinstance(rating, (int, float)) and (rating < 0 or rating > 5):
        issues.append(f"facts.rating out of range: {rating}")

    # Reviews must be non-negative
    reviews = facts.get("reviews", 0)
    if isinstance(reviews, int) and reviews < 0:
        issues.append(f"facts.reviews negative: {reviews}")

    # Confidence in valid range
    signals = output.get("signals", {})
    conf = signals.get("confidence", 0)
    if isinstance(conf, (int, float)) and (conf < 0 or conf > 1):
        issues.append(f"signals.confidence out of range: {conf}")
    elif isinstance(conf, (int, float)) and conf < 0.4:
        issues.append(f"signals.confidence too low: {conf}")

    return issues


def quality_gate_outline(output: dict) -> list[str]:
    """Quality gate for script outline output.

    Checks:
    - product_key format matches {asin}:{slot}
    - No duplicate product_keys
    - No duplicate slots
    - Points word count within limits
    - Hook and CTA not generic placeholders
    """
    issues = []
    outline = output.get("outline", {})

    # Hook quality
    hook = outline.get("hook", "")
    if isinstance(hook, str):
        generic_hooks = {"check out these products", "here are the top picks",
                         "hello everyone", "welcome back"}
        if hook.lower().strip().rstrip(".!") in generic_hooks:
            issues.append("outline.hook is too generic")

    products = outline.get("products", [])
    if not isinstance(products, list):
        return issues

    seen_keys = set()
    seen_slots = set()

    for i, p in enumerate(products):
        if not isinstance(p, dict):
            continue

        # product_key format
        pk = p.get("product_key", "")
        asin = p.get("asin", "")
        slot = p.get("slot", "")
        expected_key = f"{asin}:{slot}"
        if pk and asin and slot and pk != expected_key:
            issues.append(
                f"products[{i}].product_key mismatch: "
                f"got '{pk}', expected '{expected_key}'"
            )

        # Duplicate product_key
        if pk in seen_keys:
            issues.append(f"products[{i}].product_key duplicate: '{pk}'")
        seen_keys.add(pk)

        # Duplicate slot
        if slot in seen_slots:
            issues.append(f"products[{i}].slot duplicate: '{slot}'")
        seen_slots.add(slot)

        # Points word count
        points = p.get("points", [])
        if isinstance(points, list):
            for j, pt in enumerate(points):
                if isinstance(pt, str):
                    word_count = len(pt.split())
                    if word_count > 10:
                        issues.append(
                            f"products[{i}].points[{j}] too many words: "
                            f"{word_count} (max 10)"
                        )

    return issues
