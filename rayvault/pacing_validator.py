#!/usr/bin/env python3
"""RayVault Pacing Validator — static editorial quality gate.

Validates 05_render_config.json against editorial invariants WITHOUT
opening any video files. Pure JSON analysis.

Invariants checked:
  FAIL:
    - Total duration outside [TARGET_MIN_SEC, TARGET_MAX_SEC]
    - Any segment with end_sec <= start_sec
    - Any static segment > MAX_STATIC_SECONDS without visual change
    - segment_id inconsistency (recomputed != existing)
    - Timeline gaps or overlaps (segments not contiguous)
  WARN:
    - Motion group repetition near limit
    - Low visual type variety (>70% same type)
    - No filler when duration < TARGET_MIN_SEC

Usage:
    python3 -m rayvault.pacing_validator --config state/runs/RUN/05_render_config.json

Exit codes:
    0: all invariants pass
    1: runtime error
    2: one or more FAIL invariants violated
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from rayvault.policies import (
    TARGET_MIN_SEC,
    TARGET_MAX_SEC,
    MAX_STATIC_SECONDS,
    MIN_MOTION_SCALE,
    MIN_MOTION_POS_FRAC,
    MOTION_MAX_CONSECUTIVE_SAME,
    MIN_SEGMENT_TYPE_VARIETY,
    motion_group_for_preset,
)
from rayvault.segment_id import validate_segment_ids


# ---------------------------------------------------------------------------
# Visual change detection
# ---------------------------------------------------------------------------


def segment_has_visual_change(segment: Dict[str, Any]) -> bool:
    """Determine if a segment has inherent visual change (motion, broll, etc).

    A segment has visual change if ANY of:
      1. Mode is BROLL_VIDEO (video has inherent motion)
      2. Motion params exceed minimum thresholds
      3. Overlay event is non-static (enter/exit)
    """
    visual = segment.get("visual", {})
    mode = visual.get("mode", "")

    # BROLL_VIDEO always has motion
    if mode == "BROLL_VIDEO":
        return True

    # Check motion params
    motion = segment.get("motion", {})
    if motion:
        start_scale = motion.get("start_scale", 1.0)
        end_scale = motion.get("end_scale", 1.0)
        if abs(end_scale - start_scale) >= MIN_MOTION_SCALE:
            return True

        start_pos = motion.get("start_pos", {})
        end_pos = motion.get("end_pos", {})
        dx = abs(end_pos.get("x", 0) - start_pos.get("x", 0))
        dy = abs(end_pos.get("y", 0) - start_pos.get("y", 0))
        if dx >= MIN_MOTION_POS_FRAC or dy >= MIN_MOTION_POS_FRAC:
            return True

    # KEN_BURNS mode implies motion (from resolve_bridge patterns)
    if mode == "KEN_BURNS":
        return True

    # Overlay events (enter/exit)
    for ref in segment.get("overlay_refs", []):
        event = ref.get("event", "static")
        if event in ("enter", "exit"):
            return True

    return False


# ---------------------------------------------------------------------------
# Invariant checks
# ---------------------------------------------------------------------------


def check_duration_range(segments: List[Dict[str, Any]]) -> List[str]:
    """FAIL if total duration is outside target range."""
    if not segments:
        return ["EMPTY_TIMELINE: no segments"]

    total = max(s.get("t1", s.get("end_sec", 0)) for s in segments)
    errors = []

    if total < TARGET_MIN_SEC:
        errors.append(
            f"DURATION_SHORT: {total:.1f}s < min {TARGET_MIN_SEC}s"
        )
    if total > TARGET_MAX_SEC:
        errors.append(
            f"DURATION_LONG: {total:.1f}s > max {TARGET_MAX_SEC}s"
        )
    return errors


def check_segment_ordering(segments: List[Dict[str, Any]]) -> List[str]:
    """FAIL if any segment has end <= start, or segments overlap/gap."""
    errors = []

    for i, seg in enumerate(segments):
        t0 = seg.get("t0", seg.get("start_sec", 0))
        t1 = seg.get("t1", seg.get("end_sec", 0))
        seg_id = seg.get("id", seg.get("segment_id", f"idx_{i}"))

        if t1 <= t0:
            errors.append(
                f"INVALID_SEGMENT: {seg_id} has end({t1}) <= start({t0})"
            )

        # Check gap/overlap with previous segment
        if i > 0:
            prev = segments[i - 1]
            prev_t1 = prev.get("t1", prev.get("end_sec", 0))
            gap = abs(t0 - prev_t1)
            if gap > 0.01:  # Allow tiny floating point drift
                errors.append(
                    f"TIMELINE_GAP: between {segments[i-1].get('id', f'idx_{i-1}')} "
                    f"and {seg_id}: gap={gap:.3f}s"
                )

    return errors


def check_max_static(segments: List[Dict[str, Any]]) -> List[str]:
    """FAIL if any segment exceeds MAX_STATIC_SECONDS without visual change."""
    errors = []

    for seg in segments:
        seg_type = seg.get("type", "")
        if seg_type in ("intro", "outro"):
            continue

        t0 = seg.get("t0", seg.get("start_sec", 0))
        t1 = seg.get("t1", seg.get("end_sec", 0))
        duration = t1 - t0

        if duration > MAX_STATIC_SECONDS and not segment_has_visual_change(seg):
            seg_id = seg.get("id", seg.get("segment_id", "?"))
            errors.append(
                f"LONG_STATIC: {seg_id} is {duration:.1f}s without visual change "
                f"(max={MAX_STATIC_SECONDS}s)"
            )

    return errors


def check_motion_hygiene(segments: List[Dict[str, Any]]) -> List[str]:
    """WARN if same motion group repeats more than MOTION_MAX_CONSECUTIVE_SAME times."""
    warnings = []
    consecutive = 0
    last_group = ""

    for seg in segments:
        if seg.get("type") in ("intro", "outro"):
            consecutive = 0
            last_group = ""
            continue

        motion = seg.get("motion", {})
        preset = motion.get("preset", "")
        if not preset:
            visual = seg.get("visual", {})
            mode = visual.get("mode", "")
            if mode == "KEN_BURNS":
                preset = mode.lower()

        if not preset:
            consecutive = 0
            last_group = ""
            continue

        group = motion_group_for_preset(preset)
        if group == last_group and group != "other":
            consecutive += 1
            if consecutive >= MOTION_MAX_CONSECUTIVE_SAME:
                seg_id = seg.get("id", seg.get("segment_id", "?"))
                warnings.append(
                    f"MOTION_REPETITION: {consecutive + 1}x '{group}' in a row "
                    f"at {seg_id} (max={MOTION_MAX_CONSECUTIVE_SAME})"
                )
        else:
            consecutive = 0

        last_group = group

    return warnings


def check_type_variety(segments: List[Dict[str, Any]]) -> List[str]:
    """WARN if visual type variety is too low."""
    warnings = []
    product_segs = [s for s in segments if s.get("type") == "product"]

    if not product_segs:
        return warnings

    modes = [s.get("visual", {}).get("mode", "SKIP") for s in product_segs]
    mode_counts: Dict[str, int] = {}
    for m in modes:
        mode_counts[m] = mode_counts.get(m, 0) + 1

    total = len(modes)
    active_modes = {m for m in mode_counts if m != "SKIP"}

    if len(active_modes) < MIN_SEGMENT_TYPE_VARIETY and total > 2:
        warnings.append(
            f"LOW_VARIETY: only {len(active_modes)} visual type(s) "
            f"({', '.join(sorted(active_modes)) or 'none'})"
        )

    # Warn if any single type > 70%
    for mode, count in mode_counts.items():
        if mode != "SKIP" and count / total > 0.7:
            warnings.append(
                f"TYPE_DOMINANCE: {mode} is {count}/{total} "
                f"({count/total*100:.0f}%)"
            )

    return warnings


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------


def validate_pacing(
    config: Dict[str, Any],
    strict_duration: bool = False,
) -> Dict[str, Any]:
    """Run all pacing invariants on a render config.

    Args:
        config: parsed 05_render_config.json
        strict_duration: if True, enforce TARGET_MIN/MAX_SEC

    Returns:
        {
            "ok": bool,  # True if no FAIL errors
            "errors": [...],
            "warnings": [...],
            "summary": {duration, segment_count, type_distribution, motion_distribution},
        }
    """
    segments = config.get("segments", [])
    errors: List[str] = []
    warnings: List[str] = []

    # Duration range (strict mode or advisory)
    duration_issues = check_duration_range(segments)
    if strict_duration:
        errors.extend(duration_issues)
    else:
        warnings.extend(duration_issues)

    # Segment ordering (gaps, overlaps, end<=start)
    errors.extend(check_segment_ordering(segments))

    # Max static duration
    errors.extend(check_max_static(segments))

    # Segment ID consistency
    id_errors = validate_segment_ids(segments)
    errors.extend(id_errors)

    # Motion hygiene (advisory)
    warnings.extend(check_motion_hygiene(segments))

    # Type variety (advisory)
    warnings.extend(check_type_variety(segments))

    # Summary stats
    total_duration = max(
        (s.get("t1", s.get("end_sec", 0)) for s in segments), default=0,
    )
    type_dist: Dict[str, int] = {}
    motion_dist: Dict[str, int] = {}
    for seg in segments:
        seg_type = seg.get("type", "unknown")
        type_dist[seg_type] = type_dist.get(seg_type, 0) + 1

        visual = seg.get("visual", {})
        mode = visual.get("mode", "")
        if mode:
            motion_dist[mode] = motion_dist.get(mode, 0) + 1

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "duration_sec": round(total_duration, 2),
            "segment_count": len(segments),
            "type_distribution": type_dist,
            "motion_distribution": motion_dist,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="RayVault Pacing Validator — static editorial quality gate",
    )
    ap.add_argument("--config", required=True, help="Path to 05_render_config.json")
    ap.add_argument(
        "--strict-duration",
        action="store_true",
        help="Enforce 8-12 min duration as FAIL (default: WARN)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Output full report as JSON",
    )
    args = ap.parse_args(argv)

    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except Exception as e:
        print(f"Failed to parse config: {e}", file=sys.stderr)
        return 1

    result = validate_pacing(config, strict_duration=args.strict_duration)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = "PASS" if result["ok"] else "FAIL"
        summary = result["summary"]
        print(
            f"pacing_validator: {status} | "
            f"duration={summary['duration_sec']:.1f}s | "
            f"segments={summary['segment_count']}"
        )
        for err in result["errors"]:
            print(f"  FAIL: {err}")
        for warn in result["warnings"]:
            print(f"  WARN: {warn}")

    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
