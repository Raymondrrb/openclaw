#!/usr/bin/env python3
"""
Variation Quality Checks — Validates that scripts achieve meaningful variation.

Used by script_quality_gate.py when a variation_plan is present.

Checks:
  1. Variation score meets minimum threshold
  2. Script uses enough distinct segment types
  3. Narration n-gram similarity vs recent scripts is below threshold
  4. Disclosure text is present in the script
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# 1. Variation score check
# ---------------------------------------------------------------------------

def check_variation_score(variation_plan: Dict, min_score: float = 0.6) -> List[Dict]:
    """Check that the variation plan achieved minimum diversity score."""
    violations = []
    score = variation_plan.get("variation_score", 0.0)
    if score < min_score:
        violations.append({
            "line": 0,
            "type": "low_variation_score",
            "rule": f"Variation score {score:.2f} below minimum {min_score:.2f}",
            "excerpt": f"selections: {list(variation_plan.get('selections', {}).values())[:4]}",
            "severity": "HIGH",
        })
    return violations


# ---------------------------------------------------------------------------
# 2. Unique segment types check
# ---------------------------------------------------------------------------

def check_unique_segment_types(script_data: Dict, min_types: int = 6) -> List[Dict]:
    """Check that the script uses enough distinct segment types."""
    violations = []
    segments = script_data.get("segments", [])

    # Handle both structured formats (pipeline.py and step_1 format)
    types_found = set()
    for seg in segments:
        seg_type = seg.get("type", "")
        if seg_type:
            types_found.add(seg_type)
        # Also check nested segments (pipeline.py PRODUCT_BLOCK format)
        for sub in seg.get("segments", []):
            kind = sub.get("kind", "")
            if kind:
                types_found.add(kind)

    if len(types_found) < min_types:
        violations.append({
            "line": 0,
            "type": "low_segment_variety",
            "rule": f"Only {len(types_found)} unique segment types (minimum {min_types})",
            "excerpt": f"types: {sorted(types_found)}",
            "severity": "MEDIUM",
        })
    return violations


# ---------------------------------------------------------------------------
# 3. N-gram similarity check
# ---------------------------------------------------------------------------

def _extract_narration_text(script_data: Dict) -> str:
    """Extract all narration/voice text from a script."""
    parts = []
    for seg in script_data.get("segments", []):
        narration = seg.get("narration", "") or seg.get("voice_text", "")
        if narration:
            parts.append(narration)
        for sub in seg.get("segments", []):
            sub_text = sub.get("narration", "") or sub.get("voice_text", "")
            if sub_text:
                parts.append(sub_text)
    # Also try structure key (pipeline.py format)
    for seg in script_data.get("structure", []):
        voice = seg.get("voice_text", "")
        if voice:
            parts.append(voice)
        for sub in seg.get("segments", []):
            sub_voice = sub.get("voice_text", "")
            if sub_voice:
                parts.append(sub_voice)
    return " ".join(parts)


def _ngrams(text: str, n: int = 3) -> List[str]:
    """Extract word-level n-grams from text."""
    words = re.findall(r"[a-z]+", text.lower())
    if len(words) < n:
        return []
    return [" ".join(words[i:i + n]) for i in range(len(words) - n + 1)]


def _ngram_similarity(text_a: str, text_b: str, n: int = 3) -> float:
    """Compute Jaccard similarity of n-gram sets."""
    grams_a = set(_ngrams(text_a, n))
    grams_b = set(_ngrams(text_b, n))
    if not grams_a or not grams_b:
        return 0.0
    intersection = len(grams_a & grams_b)
    union = len(grams_a | grams_b)
    return intersection / union if union > 0 else 0.0


def check_ngram_similarity(narration: str, recent_scripts: List[Dict],
                           max_sim: float = 0.4) -> List[Dict]:
    """Check that narration doesn't overlap too much with recent scripts."""
    violations = []
    for i, recent in enumerate(recent_scripts):
        recent_text = _extract_narration_text(recent)
        if not recent_text:
            continue
        sim = _ngram_similarity(narration, recent_text)
        if sim > max_sim:
            recent_id = recent.get("run_id", f"script_{i}")
            violations.append({
                "line": 0,
                "type": "high_ngram_similarity",
                "rule": f"Narration {sim:.2f} similar to {recent_id} (max {max_sim})",
                "excerpt": f"trigram overlap with {recent_id}",
                "severity": "HIGH",
            })
    return violations


# ---------------------------------------------------------------------------
# 4. Disclosure presence check
# ---------------------------------------------------------------------------

def check_disclosure_presence(script_data: Dict, variation_plan: Dict) -> List[Dict]:
    """Check that the script includes the selected disclosure text."""
    violations = []
    prompt_instructions = variation_plan.get("prompt_instructions", {})
    disclosure_text = prompt_instructions.get("disclosure_text", "")
    if not disclosure_text:
        return violations

    # Get all text from the script
    all_text = _extract_narration_text(script_data).lower()

    # Check for key disclosure phrases
    has_affiliate = "affiliate" in all_text
    has_ai = "ai" in all_text and ("assistance" in all_text or "assisted" in all_text or "tools" in all_text)

    if not has_affiliate:
        violations.append({
            "line": 0,
            "type": "missing_affiliate_disclosure",
            "rule": "Script missing affiliate link disclosure",
            "excerpt": "Required: mention affiliate links in narration",
            "severity": "HIGH",
        })

    if not has_ai:
        violations.append({
            "line": 0,
            "type": "missing_ai_disclosure",
            "rule": "Script missing AI production disclosure",
            "excerpt": "Required: mention AI assistance in narration",
            "severity": "MEDIUM",
        })

    return violations


# ---------------------------------------------------------------------------
# 5. Structure adherence check
# ---------------------------------------------------------------------------

def check_structure_adherence(script_data: Dict, variation_plan: Dict) -> List[Dict]:
    """Check that the script follows the selected structure template."""
    violations = []
    selections = variation_plan.get("selections", {})
    structure = selections.get("structure_template", "classic_countdown")
    prompt = variation_plan.get("prompt_instructions", {})
    expected_segments = prompt.get("segments_per_product", [])

    if not expected_segments:
        return violations

    segments = script_data.get("segments", [])
    segment_types = [s.get("type", "") for s in segments]

    # Check that expected product segment types appear
    for expected_type in expected_segments:
        if expected_type not in segment_types:
            violations.append({
                "line": 0,
                "type": "missing_expected_segment",
                "rule": f"Structure '{structure}' expects {expected_type} segments but none found",
                "excerpt": f"found types: {sorted(set(segment_types))}",
                "severity": "MEDIUM",
            })

    return violations


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

def evaluate_variation_quality(script_data: Dict, variation_plan: Dict,
                               recent_scripts: Optional[List[Dict]] = None) -> List[Dict]:
    """Run all variation quality checks. Returns list of violation dicts."""
    recent = recent_scripts or []
    min_score = variation_plan.get("constraints", {}).get("min_variation_score", 0.6)

    all_violations = []

    # 1. Variation score
    all_violations.extend(check_variation_score(variation_plan, min_score))

    # 2. Segment type variety
    all_violations.extend(check_unique_segment_types(script_data))

    # 3. N-gram similarity
    narration = _extract_narration_text(script_data)
    if narration and recent:
        all_violations.extend(check_ngram_similarity(narration, recent))

    # 4. Disclosure presence
    all_violations.extend(check_disclosure_presence(script_data, variation_plan))

    # 5. Structure adherence
    all_violations.extend(check_structure_adherence(script_data, variation_plan))

    # Tag all violations with check source
    for v in all_violations:
        v["check"] = "variation_quality"

    return all_violations
