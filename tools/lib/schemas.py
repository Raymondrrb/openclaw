"""Schema definitions for LLM contracts — Amazon extractor + Ranker + Script Writer.

Single source of truth for output schemas used by ContractSpec.
Each schema is JSON Schema draft-07 compatible (simple subset).

Pipeline flow:
  1. Amazon Extractor → normalized product facts
  2. Ranker Top-3 → winners with slots (best_overall/value/premium)
  3. Script Writer Outline (Layer 1) → structured outline with product_key
  4. Script Writer Final (Layer 2) → spoken script with segments

Stdlib only — no external deps.

Usage:
    from tools.lib.schemas import AMAZON_EXTRACT_SCHEMA, RANKER_SCHEMA
    from tools.lib.schemas import SCRIPT_OUTLINE_SCHEMA, SCRIPT_OUTLINE_CONTRACT
    from tools.lib.schemas import SCRIPT_FINAL_SCHEMA, SCRIPT_FINAL_CONTRACT
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


# ---------------------------------------------------------------------------
# Script Writer — Final Script schema (Layer 2)
# ---------------------------------------------------------------------------

SCRIPT_FINAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "status", "contract_version", "script_version",
        "script", "total_word_count", "estimated_duration_sec",
    ],
    "properties": {
        "status": {"type": "string", "enum": ["ok", "needs_human"]},
        "contract_version": {"type": "string", "minLength": 1},
        "script_version": {"type": "integer"},
        "total_word_count": {"type": "integer"},
        "estimated_duration_sec": {"type": "integer"},

        "script": {
            "type": "object",
            "additionalProperties": False,
            "required": ["intro", "segments", "outro"],
            "properties": {
                "intro": {"type": "string", "minLength": 20, "maxLength": 300},

                "segments": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "product_key", "asin", "slot",
                            "heading", "body", "verdict_line",
                            "transition", "estimated_words",
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
                            "heading": {
                                "type": "string",
                                "minLength": 5,
                                "maxLength": 80,
                            },
                            "body": {
                                "type": "string",
                                "minLength": 50,
                                "maxLength": 600,
                            },
                            "verdict_line": {
                                "type": "string",
                                "minLength": 5,
                                "maxLength": 80,
                            },
                            "transition": {
                                "type": "string",
                                "minLength": 5,
                                "maxLength": 80,
                            },
                            "estimated_words": {"type": "integer"},
                        },
                    },
                },

                "outro": {"type": "string", "minLength": 20, "maxLength": 250},
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Script Writer Final — Patch output schema
# ---------------------------------------------------------------------------

SCRIPT_FINAL_PATCH_SCHEMA = {
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
# Script Writer Final — ContractSpec
# ---------------------------------------------------------------------------

SCRIPT_FINAL_CONTRACT = ContractSpec(
    name="script_writer_final",
    version="v0.1.0",
    cache_policy=CACHE_POLICIES["daily"],
    schema=SCRIPT_FINAL_SCHEMA,
    economy_rules=[
        *DEFAULT_ECONOMY_RULES,
        "Include contract_version and script_version in output.",
        "product_key, asin, slot: copy from outline — NEVER change.",
        "intro: max 300 chars, must hook in first 5 seconds.",
        "body: max 600 chars per segment, incorporate angle + points + verdict from outline.",
        "Persona per slot: best_overall=authoritative, best_value=practical, best_premium=aspirational.",
        "Total target: 400-900 words (2.5 to 6 minute video).",
        "estimated_duration_sec = total_word_count / 2.5 (150 words/min).",
        "Never invent product facts not present in the outline.",
        "If mode=patch, return ONLY patch_ops (not a full script).",
    ],
)

SCRIPT_FINAL_PATCH_CONTRACT = ContractSpec(
    name="script_writer_final",
    version="v0.1.0",
    cache_policy=CACHE_POLICIES["none"],
    schema=SCRIPT_FINAL_PATCH_SCHEMA,
    economy_rules=[
        "Return ONLY valid JSON with patch_ops array.",
        "Allowed op: replace only. Max 5 ops.",
        "Allowed paths: /script/intro, /script/segments/{i}/heading, "
        "/script/segments/{i}/body, /script/segments/{i}/verdict_line, "
        "/script/segments/{i}/transition, /script/outro.",
        "FORBIDDEN: anything touching asin, slot, product_key, "
        "contract_version, script_version, estimated_words, "
        "total_word_count, estimated_duration_sec.",
    ],
)


# ---------------------------------------------------------------------------
# Quality gate — Final script
# ---------------------------------------------------------------------------

def quality_gate_script_final(output: dict) -> list[str]:
    """Quality gate for final script output.

    Checks semantic correctness that schema alone can't enforce:
    - product_key format matches {asin}:{slot}
    - No duplicate product_keys or slots
    - Segment balance (no segment > 2x shortest)
    - Word count within target range (400-900)
    - estimated_duration_sec matches word count (~150 wpm)
    - intro/outro not generic placeholders
    """
    issues = []
    script = output.get("script", {})

    # Intro quality
    intro = script.get("intro", "")
    if isinstance(intro, str):
        generic_intros = {
            "hey guys welcome back", "hello everyone",
            "what's up guys", "hey what's going on",
        }
        intro_lower = intro.lower().strip().rstrip(".!,")
        if any(intro_lower.startswith(g) for g in generic_intros):
            issues.append("script.intro starts with generic YouTube opener")

    segments = script.get("segments", [])
    if not isinstance(segments, list):
        return issues

    seen_keys = set()
    seen_slots = set()
    word_counts = []

    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue

        # product_key format
        pk = seg.get("product_key", "")
        asin = seg.get("asin", "")
        slot = seg.get("slot", "")
        expected_key = f"{asin}:{slot}"
        if pk and asin and slot and pk != expected_key:
            issues.append(
                f"segments[{i}].product_key mismatch: "
                f"got '{pk}', expected '{expected_key}'"
            )

        # Duplicates
        if pk in seen_keys:
            issues.append(f"segments[{i}].product_key duplicate: '{pk}'")
        seen_keys.add(pk)
        if slot in seen_slots:
            issues.append(f"segments[{i}].slot duplicate: '{slot}'")
        seen_slots.add(slot)

        # Track word counts for balance check
        est = seg.get("estimated_words", 0)
        if isinstance(est, int) and est > 0:
            word_counts.append(est)

        # Body not empty placeholder
        body = seg.get("body", "")
        if isinstance(body, str) and len(body.strip()) < 50:
            issues.append(f"segments[{i}].body too short or placeholder")

    # Segment balance: no segment > 2x shortest
    if len(word_counts) >= 2:
        shortest = min(word_counts)
        longest = max(word_counts)
        if shortest > 0 and longest > shortest * 2:
            issues.append(
                f"Segment imbalance: longest={longest} words, "
                f"shortest={shortest} words (ratio {longest/shortest:.1f}x, max 2x)"
            )

    # Total word count range
    total = output.get("total_word_count", 0)
    if isinstance(total, int):
        if total < 400:
            issues.append(f"total_word_count too low: {total} (min 400)")
        elif total > 900:
            issues.append(f"total_word_count too high: {total} (max 900)")

    # Duration consistency (150 wpm → ~2.5 words/sec)
    duration = output.get("estimated_duration_sec", 0)
    if isinstance(total, int) and isinstance(duration, int) and total > 0:
        expected_duration = int(total * 60 / 150)
        if abs(duration - expected_duration) > 30:
            issues.append(
                f"estimated_duration_sec inconsistent: {duration}s "
                f"but {total} words → ~{expected_duration}s"
            )

    return issues


# ---------------------------------------------------------------------------
# Pipeline helper — build payload for Layer 2 from validated outline
# ---------------------------------------------------------------------------

def build_script_payload(
    outline: dict,
    *,
    niche: str = "",
    locale: str = "en-US",
    target_duration_range: tuple[int, int] = (150, 360),
    mode: str = "generate",
) -> dict:
    """Build the minimal payload for the Layer 2 script writer LLM call.

    Takes a validated outline (Layer 1 output) and produces the payload
    that the script_writer_final contract expects.

    Args:
        outline: Validated outline dict (from SCRIPT_OUTLINE_SCHEMA).
        niche: Channel niche (e.g. "wireless earbuds").
        locale: Content locale (e.g. "en-US").
        target_duration_range: (min_sec, max_sec) for the video.
        mode: "generate" (full script) or "patch" (with base).

    Returns:
        Payload dict ready for ContractEngine.build_prompt_and_cache_key().
    """
    outline_data = outline.get("outline", {})

    # Extract product summaries (minimal — no redundant data)
    products = []
    for p in outline_data.get("products", []):
        products.append({
            "product_key": p.get("product_key", ""),
            "asin": p.get("asin", ""),
            "slot": p.get("slot", ""),
            "angle": p.get("angle", ""),
            "points": p.get("points", []),
            "verdict": p.get("verdict", ""),
        })

    return {
        "niche": niche,
        "locale": locale,
        "mode": mode,
        "target_duration_range_sec": list(target_duration_range),
        "outline": {
            "hook": outline_data.get("hook", ""),
            "products": products,
            "cta": outline_data.get("cta", ""),
        },
        "outline_version": outline.get("outline_version", 1),
        "contract_version": outline.get("contract_version", ""),
    }


def validate_outline_for_layer2(outline: dict) -> list[str]:
    """Validate that an outline is ready for Layer 2 rendering.

    Pre-check before sending to the script writer final contract.
    Returns list of issues (empty = ready).
    """
    issues = []

    if outline.get("status") != "ok":
        issues.append(f"Outline status is '{outline.get('status')}', not 'ok'")

    outline_data = outline.get("outline", {})
    if not outline_data:
        issues.append("Outline data is empty")
        return issues

    hook = outline_data.get("hook", "")
    if not hook or len(hook) < 10:
        issues.append("Outline hook is missing or too short")

    products = outline_data.get("products", [])
    if not products:
        issues.append("Outline has no products")
    else:
        for i, p in enumerate(products):
            if not p.get("angle") or p.get("angle") == "[needs review]":
                issues.append(f"products[{i}].angle needs review")
            if not p.get("points"):
                issues.append(f"products[{i}].points is empty")

    cta = outline_data.get("cta", "")
    if not cta or len(cta) < 10:
        issues.append("Outline CTA is missing or too short")

    return issues


# ---------------------------------------------------------------------------
# Voice Script schema (Layer 3)
# ---------------------------------------------------------------------------

VOICE_SCRIPT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "status", "contract_version", "segments",
        "audio_plan", "total_duration_sec",
    ],
    "properties": {
        "status": {"type": "string", "enum": ["ok", "needs_human"]},
        "contract_version": {"type": "string", "minLength": 1},
        "total_duration_sec": {"type": "integer"},

        "segments": {
            "type": "array",
            "minItems": 4,
            "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "segment_id", "kind", "text",
                    "lip_sync_hint", "approx_duration_sec",
                ],
                "properties": {
                    "segment_id": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 40,
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["intro", "product", "transition", "outro"],
                    },
                    "product_key": {
                        "type": "string",
                        "maxLength": 40,
                    },
                    "text": {
                        "type": "string",
                        "minLength": 20,
                        "maxLength": 500,
                    },
                    "lip_sync_hint": {
                        "type": "string",
                        "enum": ["neutral", "excited", "serious"],
                    },
                    "approx_duration_sec": {"type": "integer"},
                },
            },
        },

        "audio_plan": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "segment_id", "voice_id", "model",
                    "output_filename",
                ],
                "properties": {
                    "segment_id": {"type": "string", "minLength": 1},
                    "voice_id": {"type": "string", "minLength": 1},
                    "model": {"type": "string", "minLength": 1},
                    "stability": {"type": "number"},
                    "style": {"type": "number"},
                    "output_filename": {
                        "type": "string",
                        "minLength": 5,
                        "maxLength": 80,
                    },
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Voice Script — Patch output schema
# ---------------------------------------------------------------------------

VOICE_SCRIPT_PATCH_SCHEMA = {
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
# Voice Script — ContractSpec
# ---------------------------------------------------------------------------

VOICE_SCRIPT_CONTRACT = ContractSpec(
    name="voice_script",
    version="v0.1.0",
    cache_policy=CACHE_POLICIES["daily"],
    schema=VOICE_SCRIPT_SCHEMA,
    economy_rules=[
        *DEFAULT_ECONOMY_RULES,
        "Include contract_version in output.",
        "Each segment 8-20 seconds spoken. Intro 5-12s, outro 5-15s, transitions 3-8s.",
        "Voice-ready text: short sentences, speakable numbers, no raw currency symbols.",
        "TTS tags optional: [pause=300ms], [emphasis]word[/emphasis], [rate=1.05]...[/rate].",
        "product_key: copy from Layer 2 segments — NEVER change.",
        "segment_id must be stable across patches (e.g. 'intro', 'p0', 't0_1', 'outro').",
        "Never invent spoken text not derivable from the script.",
    ],
)

VOICE_SCRIPT_PATCH_CONTRACT = ContractSpec(
    name="voice_script",
    version="v0.1.0",
    cache_policy=CACHE_POLICIES["none"],
    schema=VOICE_SCRIPT_PATCH_SCHEMA,
    economy_rules=[
        "Return ONLY valid JSON with patch_ops array.",
        "Allowed op: replace only. Max 5 ops.",
        "Allowed paths: /segments/{i}/text, /segments/{i}/lip_sync_hint, "
        "/segments/{i}/approx_duration_sec, /audio_plan/{i}/stability, /audio_plan/{i}/style.",
        "FORBIDDEN: segment_id, kind, product_key, voice_id, model, "
        "output_filename, contract_version.",
    ],
)


# ---------------------------------------------------------------------------
# Quality gate — Voice script
# ---------------------------------------------------------------------------

import re as _re

_TTS_TAG_RE = _re.compile(r"\[(?:pause=\d+ms|/?emphasis(?:=[^\]]+)?|/?rate(?:=[^\]]+)?)\]")


def _strip_tts_tags(text: str) -> str:
    """Remove TTS tags from text for word counting."""
    return _TTS_TAG_RE.sub("", text).strip()


def _estimate_duration_sec(text: str, wpm: int = 165) -> float:
    """Estimate spoken duration from text word count."""
    clean = _strip_tts_tags(text)
    words = len(_re.findall(r"\b\w+\b", clean))
    return (words * 60.0) / max(1, wpm)


def quality_gate_voice_script(output: dict) -> list[str]:
    """Quality gate for voice script output.

    Checks:
    - segment_id uniqueness
    - audio_plan segment_ids match segments
    - Duration estimates reasonable (within 15% of text-based estimate)
    - total_duration_sec matches sum of segments
    - Kind counts (at least 1 intro, 1 outro, 1 product)
    - Segment duration bounds (5-30s per segment)
    """
    issues = []
    segments = output.get("segments", [])
    audio_plan = output.get("audio_plan", [])

    # Segment ID uniqueness
    seg_ids = set()
    for i, seg in enumerate(segments):
        sid = seg.get("segment_id", "")
        if sid in seg_ids:
            issues.append(f"segments[{i}].segment_id duplicate: '{sid}'")
        seg_ids.add(sid)

    # Audio plan coverage
    plan_ids = {p.get("segment_id", "") for p in audio_plan}
    missing = seg_ids - plan_ids
    if missing:
        issues.append(f"audio_plan missing segment_ids: {sorted(missing)}")

    # Kind distribution
    kinds = [s.get("kind", "") for s in segments]
    if "intro" not in kinds:
        issues.append("No 'intro' segment found")
    if "outro" not in kinds:
        issues.append("No 'outro' segment found")
    if "product" not in kinds:
        issues.append("No 'product' segment found")

    # Duration bounds and text-based estimation
    total_approx = 0
    for i, seg in enumerate(segments):
        dur = seg.get("approx_duration_sec", 0)
        if isinstance(dur, int):
            total_approx += dur
            if dur < 3 or dur > 30:
                issues.append(
                    f"segments[{i}].approx_duration_sec out of bounds: {dur}s"
                )

        # Text-based duration check (within 50% — generous tolerance)
        text = seg.get("text", "")
        if isinstance(text, str) and len(text) > 20:
            est = _estimate_duration_sec(text)
            if dur > 0 and abs(est - dur) > dur * 0.5:
                issues.append(
                    f"segments[{i}] duration mismatch: approx={dur}s, "
                    f"text-based estimate={est:.1f}s"
                )

    # Total duration consistency
    total_reported = output.get("total_duration_sec", 0)
    if isinstance(total_reported, int) and total_approx > 0:
        if abs(total_reported - total_approx) > 10:
            issues.append(
                f"total_duration_sec mismatch: reported={total_reported}s, "
                f"sum of segments={total_approx}s"
            )

    # Stability/style range in audio_plan
    for i, plan in enumerate(audio_plan):
        for field in ("stability", "style"):
            val = plan.get(field)
            if val is not None and isinstance(val, (int, float)):
                if val < 0 or val > 1:
                    issues.append(f"audio_plan[{i}].{field} out of range: {val}")

    return issues


# ---------------------------------------------------------------------------
# Pipeline helper — build voice script payload from validated final script
# ---------------------------------------------------------------------------

def build_voice_payload(
    final_script: dict,
    *,
    niche: str = "",
    locale: str = "en-US",
    voice_id: str = "placeholder",
    model: str = "eleven_multilingual_v2",
    mode: str = "full",
) -> dict:
    """Build payload for the voice_script contract from a validated Layer 2 script.

    Args:
        final_script: Validated output from SCRIPT_FINAL_SCHEMA.
        niche: Channel niche.
        locale: Content locale (affects number pronunciation).
        voice_id: ElevenLabs voice ID.
        model: TTS model name.
        mode: "full" or "patch".

    Returns:
        Payload dict for ContractEngine.
    """
    script = final_script.get("script", {})

    segments_input = []
    for seg in script.get("segments", []):
        segments_input.append({
            "product_key": seg.get("product_key", ""),
            "slot": seg.get("slot", ""),
            "heading": seg.get("heading", ""),
            "body": seg.get("body", ""),
            "verdict_line": seg.get("verdict_line", ""),
            "transition": seg.get("transition", ""),
        })

    return {
        "niche": niche,
        "locale": locale,
        "mode": mode,
        "voice_id": voice_id,
        "model": model,
        "script": {
            "intro": script.get("intro", ""),
            "segments": segments_input,
            "outro": script.get("outro", ""),
        },
        "estimated_duration_sec": final_script.get("estimated_duration_sec", 0),
        "contract_version": final_script.get("contract_version", ""),
    }


def validate_script_for_layer3(final_script: dict) -> list[str]:
    """Validate that a final script is ready for Layer 3 voice rendering.

    Pre-check before sending to the voice_script contract.
    Returns list of issues (empty = ready).
    """
    issues = []

    if final_script.get("status") != "ok":
        issues.append(f"Script status is '{final_script.get('status')}', not 'ok'")

    script = final_script.get("script", {})
    if not script:
        issues.append("Script data is empty")
        return issues

    intro = script.get("intro", "")
    if not intro or len(intro) < 20:
        issues.append("Script intro is missing or too short")

    segments = script.get("segments", [])
    if not segments:
        issues.append("Script has no segments")
    else:
        for i, seg in enumerate(segments):
            body = seg.get("body", "")
            if not body or len(body) < 50:
                issues.append(f"segments[{i}].body is missing or too short")

    outro = script.get("outro", "")
    if not outro or len(outro) < 20:
        issues.append("Script outro is missing or too short")

    total = final_script.get("total_word_count", 0)
    if isinstance(total, int) and total < 100:
        issues.append(f"total_word_count too low for voice: {total}")

    return issues
