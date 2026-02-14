"""Tone Gate — pre-TTS duration validation and auto-repair.

Validates that voice script segments have reasonable spoken duration
before spending TTS credits. Uses word-per-minute (WPM) estimation
which is more stable than chars-per-second.

Strategy:
  1. Strip TTS tags ([pause=], [emphasis], [rate=])
  2. Count words → estimate duration at WPM rate
  3. Compare against segment's approx_duration_sec
  4. If over budget: return repair suggestions (not full regeneration)
  5. After 2 repair attempts: needs_human

Stdlib only — no external deps.

Usage:
    from tools.lib.tone_gate import tone_gate_validate, ToneGateRules
    from tools.lib.tone_gate import estimate_duration_sec, strip_tts_tags

    rules = ToneGateRules()
    violations = tone_gate_validate(segments, rules)
    if violations:
        repair_prompt = build_tone_repair_prompt(violations)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List

# TTS tag patterns
_TTS_TAG_RE = re.compile(
    r"\[(?:pause=\d+m?s|/?emphasis(?:=[^\]]+)?|/?rate(?:=[^\]]+)?)\]"
)


def strip_tts_tags(text: str) -> str:
    """Remove TTS inline tags for accurate word counting."""
    return _TTS_TAG_RE.sub("", text).strip()


def count_words(text: str) -> int:
    """Count speakable words in text (after stripping tags)."""
    clean = strip_tts_tags(text)
    return len(re.findall(r"\b\w+\b", clean))


def estimate_duration_sec(text: str, wpm: int = 165) -> float:
    """Estimate spoken duration in seconds from text.

    Default WPM of 165 is typical for narrated YouTube content
    (normal narration is 155-175 WPM).
    """
    words = count_words(text)
    return (words * 60.0) / max(1, wpm)


@dataclass(frozen=True)
class ToneGateRules:
    """Configuration for tone gate validation.

    Args:
        wpm: Words per minute for duration estimation.
        max_overage_ratio: Max ratio of estimated/approx duration (1.15 = +15%).
        min_words_per_segment: Minimum words for any segment.
        max_words_per_segment: Maximum words for any segment.
    """
    wpm: int = 165
    max_overage_ratio: float = 1.15
    min_words_per_segment: int = 5
    max_words_per_segment: int = 80


@dataclass
class ToneViolation:
    """A single tone gate violation."""
    segment_id: str
    kind: str
    approx_duration_sec: float
    estimated_duration_sec: float
    word_count: int
    issue: str

    @property
    def over_by_sec(self) -> float:
        return self.estimated_duration_sec - self.approx_duration_sec


def tone_gate_validate(
    segments: List[Dict[str, Any]],
    rules: ToneGateRules | None = None,
) -> List[ToneViolation]:
    """Validate voice segments against tone gate rules.

    Returns list of violations (empty = all segments pass).
    """
    rules = rules or ToneGateRules()
    violations = []

    for seg in segments:
        sid = seg.get("segment_id", "?")
        kind = seg.get("kind", "?")
        text = seg.get("text", "")
        approx = float(seg.get("approx_duration_sec", 0))

        if not text:
            continue

        words = count_words(text)
        est = estimate_duration_sec(text, rules.wpm)

        # Too many words
        if words > rules.max_words_per_segment:
            violations.append(ToneViolation(
                segment_id=sid, kind=kind,
                approx_duration_sec=approx,
                estimated_duration_sec=est,
                word_count=words,
                issue=f"Too many words: {words} (max {rules.max_words_per_segment})",
            ))
            continue

        # Too few words
        if words < rules.min_words_per_segment:
            violations.append(ToneViolation(
                segment_id=sid, kind=kind,
                approx_duration_sec=approx,
                estimated_duration_sec=est,
                word_count=words,
                issue=f"Too few words: {words} (min {rules.min_words_per_segment})",
            ))
            continue

        # Duration overage
        if approx > 0 and est > approx * rules.max_overage_ratio:
            violations.append(ToneViolation(
                segment_id=sid, kind=kind,
                approx_duration_sec=approx,
                estimated_duration_sec=round(est, 2),
                word_count=words,
                issue=(
                    f"Text too long for stated duration: "
                    f"~{est:.1f}s vs {approx}s approx "
                    f"(+{est - approx:.1f}s over)"
                ),
            ))

    return violations


def build_tone_repair_prompt(violations: List[ToneViolation]) -> str:
    """Build a targeted repair prompt for tone gate violations.

    Instead of regenerating the full voice script, asks the LLM to
    shorten only the specific segments that are too long.
    """
    lines = ["### TONE GATE REPAIR REQUEST",
             "The following voice segments exceed their duration budget.",
             "Shorten ONLY these segments. Keep meaning. Return patch_ops.",
             ""]

    for v in violations:
        lines.append(
            f"- segment_id={v.segment_id!r} ({v.kind}): "
            f"{v.issue} ({v.word_count} words)"
        )

    lines.append("")
    lines.append("### RULES")
    lines.append("- Return ONLY patch_ops for /segments/{i}/text paths.")
    lines.append("- Do NOT change segment_id, kind, or lip_sync_hint.")
    lines.append("- Keep the core message. Cut filler words and redundancy.")
    lines.append("- Each shortened text must be valid spoken English/Portuguese.")

    return "\n".join(lines)
