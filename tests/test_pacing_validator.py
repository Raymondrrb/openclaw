#!/usr/bin/env python3
"""Tests for rayvault/pacing_validator.py — editorial quality gate."""

from __future__ import annotations

import unittest

from rayvault.pacing_validator import (
    check_duration_range,
    check_max_static,
    check_motion_hygiene,
    check_segment_ordering,
    check_type_variety,
    segment_has_visual_change,
    validate_pacing,
)
from rayvault.policies import (
    MAX_STATIC_SECONDS,
    TARGET_MAX_SEC,
    TARGET_MIN_SEC,
)


def _seg(t0: float, t1: float, **kw) -> dict:
    """Build a minimal segment with start/end time and optional overrides."""
    s = {"start_sec": t0, "end_sec": t1, "type": "product"}
    s.update(kw)
    return s


def _timeline(n: int = 20, seg_dur: float = 30.0, **kw) -> list[dict]:
    """Build a contiguous timeline of n segments, each seg_dur seconds."""
    segs = []
    for i in range(n):
        s = _seg(i * seg_dur, (i + 1) * seg_dur, id=f"seg_{i:03d}", **kw)
        segs.append(s)
    return segs


# ---------------------------------------------------------------
# segment_has_visual_change
# ---------------------------------------------------------------

class TestSegmentHasVisualChange(unittest.TestCase):

    def test_broll_video_has_change(self):
        seg = _seg(0, 10, visual={"mode": "BROLL_VIDEO"})
        self.assertTrue(segment_has_visual_change(seg))

    def test_ken_burns_has_change(self):
        seg = _seg(0, 10, visual={"mode": "KEN_BURNS"})
        self.assertTrue(segment_has_visual_change(seg))

    def test_static_image_no_change(self):
        seg = _seg(0, 10, visual={"mode": "STATIC_IMAGE"})
        self.assertFalse(segment_has_visual_change(seg))

    def test_motion_scale_exceeds_threshold(self):
        seg = _seg(0, 10, motion={"start_scale": 1.0, "end_scale": 1.1})
        self.assertTrue(segment_has_visual_change(seg))

    def test_motion_scale_below_threshold(self):
        seg = _seg(0, 10, motion={"start_scale": 1.0, "end_scale": 1.02})
        self.assertFalse(segment_has_visual_change(seg))

    def test_motion_position_exceeds_threshold(self):
        seg = _seg(0, 10, motion={
            "start_pos": {"x": 0.0, "y": 0.0},
            "end_pos": {"x": 0.1, "y": 0.0},
        })
        self.assertTrue(segment_has_visual_change(seg))

    def test_overlay_enter_has_change(self):
        seg = _seg(0, 10, overlay_refs=[{"event": "enter", "kind": "lower_third"}])
        self.assertTrue(segment_has_visual_change(seg))

    def test_overlay_exit_has_change(self):
        seg = _seg(0, 10, overlay_refs=[{"event": "exit", "kind": "price_tag"}])
        self.assertTrue(segment_has_visual_change(seg))

    def test_overlay_static_no_change(self):
        seg = _seg(0, 10, overlay_refs=[{"event": "static", "kind": "lower_third"}])
        self.assertFalse(segment_has_visual_change(seg))

    def test_no_visual_no_motion(self):
        seg = _seg(0, 10)
        self.assertFalse(segment_has_visual_change(seg))

    def test_empty_motion(self):
        seg = _seg(0, 10, motion={})
        self.assertFalse(segment_has_visual_change(seg))


# ---------------------------------------------------------------
# check_duration_range
# ---------------------------------------------------------------

class TestCheckDurationRange(unittest.TestCase):

    def test_in_range_no_errors(self):
        total = (TARGET_MIN_SEC + TARGET_MAX_SEC) / 2
        segs = [_seg(0, total)]
        errors = check_duration_range(segs)
        self.assertEqual(errors, [])

    def test_too_short(self):
        segs = [_seg(0, TARGET_MIN_SEC - 10)]
        errors = check_duration_range(segs)
        self.assertEqual(len(errors), 1)
        self.assertIn("DURATION_SHORT", errors[0])

    def test_too_long(self):
        segs = [_seg(0, TARGET_MAX_SEC + 10)]
        errors = check_duration_range(segs)
        self.assertEqual(len(errors), 1)
        self.assertIn("DURATION_LONG", errors[0])

    def test_empty_timeline(self):
        errors = check_duration_range([])
        self.assertEqual(len(errors), 1)
        self.assertIn("EMPTY_TIMELINE", errors[0])

    def test_uses_max_end_sec(self):
        """Should use the max end_sec across all segments."""
        segs = [_seg(0, 300), _seg(300, 600)]
        errors = check_duration_range(segs)
        self.assertEqual(errors, [])  # 600s is in range [480, 720]


# ---------------------------------------------------------------
# check_segment_ordering
# ---------------------------------------------------------------

class TestCheckSegmentOrdering(unittest.TestCase):

    def test_valid_ordering_no_errors(self):
        segs = [_seg(0, 10), _seg(10, 20), _seg(20, 30)]
        errors = check_segment_ordering(segs)
        self.assertEqual(errors, [])

    def test_end_before_start(self):
        segs = [_seg(10, 5)]  # end < start
        errors = check_segment_ordering(segs)
        self.assertEqual(len(errors), 1)
        self.assertIn("INVALID_SEGMENT", errors[0])

    def test_zero_duration(self):
        segs = [_seg(10, 10)]  # end == start
        errors = check_segment_ordering(segs)
        self.assertEqual(len(errors), 1)
        self.assertIn("INVALID_SEGMENT", errors[0])

    def test_gap_between_segments(self):
        segs = [_seg(0, 10), _seg(15, 25)]  # 5s gap
        errors = check_segment_ordering(segs)
        self.assertEqual(len(errors), 1)
        self.assertIn("TIMELINE_GAP", errors[0])

    def test_tiny_floating_point_drift_ok(self):
        segs = [_seg(0, 10.005), _seg(10.005, 20)]
        errors = check_segment_ordering(segs)
        self.assertEqual(errors, [])

    def test_overlap_detected(self):
        segs = [_seg(0, 12), _seg(10, 20)]  # overlap at 10-12
        errors = check_segment_ordering(segs)
        self.assertEqual(len(errors), 1)
        self.assertIn("TIMELINE_GAP", errors[0])  # Uses gap check for both

    def test_empty_no_errors(self):
        errors = check_segment_ordering([])
        self.assertEqual(errors, [])


# ---------------------------------------------------------------
# check_max_static
# ---------------------------------------------------------------

class TestCheckMaxStatic(unittest.TestCase):

    def test_short_static_ok(self):
        segs = [_seg(0, MAX_STATIC_SECONDS - 1)]
        errors = check_max_static(segs)
        self.assertEqual(errors, [])

    def test_long_static_fails(self):
        segs = [_seg(0, MAX_STATIC_SECONDS + 5, id="long_seg")]
        errors = check_max_static(segs)
        self.assertEqual(len(errors), 1)
        self.assertIn("LONG_STATIC", errors[0])

    def test_long_with_motion_ok(self):
        segs = [_seg(0, MAX_STATIC_SECONDS + 5,
                      visual={"mode": "KEN_BURNS"})]
        errors = check_max_static(segs)
        self.assertEqual(errors, [])

    def test_intro_excluded(self):
        segs = [_seg(0, MAX_STATIC_SECONDS + 5, type="intro")]
        errors = check_max_static(segs)
        self.assertEqual(errors, [])

    def test_outro_excluded(self):
        segs = [_seg(0, MAX_STATIC_SECONDS + 5, type="outro")]
        errors = check_max_static(segs)
        self.assertEqual(errors, [])


# ---------------------------------------------------------------
# check_motion_hygiene
# ---------------------------------------------------------------

class TestCheckMotionHygiene(unittest.TestCase):

    def test_varied_motion_no_warnings(self):
        segs = [
            _seg(0, 10, motion={"preset": "zoom_in_center"}),
            _seg(10, 20, motion={"preset": "pan_left_to_right"}),
            _seg(20, 30, motion={"preset": "zoom_in_center"}),
        ]
        warnings = check_motion_hygiene(segs)
        self.assertEqual(warnings, [])

    def test_repeated_same_group_warns(self):
        # Need 3+ consecutive of same group (MOTION_MAX_CONSECUTIVE_SAME = 2)
        # Use "zoom_in_center" which maps to "zoom_in" group
        segs = [
            _seg(0, 10, motion={"preset": "zoom_in_center"}),
            _seg(10, 20, motion={"preset": "slow_push_in"}),  # Same "zoom_in" group
            _seg(20, 30, motion={"preset": "push_in"}),  # Same "zoom_in" group
        ]
        warnings = check_motion_hygiene(segs)
        self.assertGreater(len(warnings), 0)
        self.assertIn("MOTION_REPETITION", warnings[0])

    def test_intro_resets_counter(self):
        segs = [
            _seg(0, 10, motion={"preset": "zoom_in_center"}),
            _seg(10, 20, type="intro"),
            _seg(20, 30, motion={"preset": "zoom_in_center"}),
        ]
        warnings = check_motion_hygiene(segs)
        self.assertEqual(warnings, [])

    def test_no_preset_resets(self):
        segs = [
            _seg(0, 10, motion={"preset": "zoom_in_center"}),
            _seg(10, 20),  # No motion
            _seg(20, 30, motion={"preset": "zoom_in_center"}),
        ]
        warnings = check_motion_hygiene(segs)
        self.assertEqual(warnings, [])


# ---------------------------------------------------------------
# check_type_variety
# ---------------------------------------------------------------

class TestCheckTypeVariety(unittest.TestCase):

    def test_varied_types_no_warnings(self):
        segs = [
            _seg(0, 10, type="product", visual={"mode": "KEN_BURNS"}),
            _seg(10, 20, type="product", visual={"mode": "BROLL_VIDEO"}),
            _seg(20, 30, type="product", visual={"mode": "STATIC_IMAGE"}),
        ]
        warnings = check_type_variety(segs)
        self.assertEqual(warnings, [])

    def test_single_mode_dominance_warns(self):
        segs = [
            _seg(i * 10, (i + 1) * 10, type="product", visual={"mode": "KEN_BURNS"})
            for i in range(5)
        ]
        warnings = check_type_variety(segs)
        self.assertGreater(len(warnings), 0)

    def test_no_product_segments_no_warnings(self):
        segs = [_seg(0, 10, type="intro"), _seg(10, 20, type="outro")]
        warnings = check_type_variety(segs)
        self.assertEqual(warnings, [])

    def test_two_segments_no_low_variety_warning(self):
        """With <= 2 segments, low variety check doesn't trigger."""
        segs = [
            _seg(0, 10, type="product", visual={"mode": "KEN_BURNS"}),
            _seg(10, 20, type="product", visual={"mode": "KEN_BURNS"}),
        ]
        warnings = check_type_variety(segs)
        # Dominance warning might fire, but low variety shouldn't
        for w in warnings:
            self.assertNotIn("LOW_VARIETY", w)


# ---------------------------------------------------------------
# validate_pacing (integration)
# ---------------------------------------------------------------

class TestValidatePacing(unittest.TestCase):

    def _make_good_config(self) -> dict:
        """Build a config that passes all checks."""
        segs = _timeline(n=20, seg_dur=30.0)  # 600s total, in range
        # Add visual change to all to avoid LONG_STATIC
        for s in segs:
            s["visual"] = {"mode": "KEN_BURNS"}
            s["motion"] = {"preset": "slow_zoom_in", "start_scale": 1.0, "end_scale": 1.1}
        # Vary motion to avoid MOTION_REPETITION (use actual presets from MOTION_GROUPS)
        presets = ["zoom_in_center", "pan_left_to_right", "slow_push_in", "pull_out", "diagonal_drift"]
        for i, s in enumerate(segs):
            s["motion"]["preset"] = presets[i % len(presets)]
        return {"segments": segs}

    def test_good_config_passes(self):
        result = validate_pacing(self._make_good_config())
        self.assertTrue(result["ok"])
        self.assertEqual(result["errors"], [])

    def test_returns_required_keys(self):
        result = validate_pacing(self._make_good_config())
        for key in ("ok", "errors", "warnings", "summary"):
            self.assertIn(key, result)

    def test_summary_has_stats(self):
        result = validate_pacing(self._make_good_config())
        summary = result["summary"]
        self.assertIn("duration_sec", summary)
        self.assertIn("segment_count", summary)
        self.assertIn("type_distribution", summary)
        self.assertIn("motion_distribution", summary)

    def test_duration_sec_correct(self):
        result = validate_pacing(self._make_good_config())
        self.assertAlmostEqual(result["summary"]["duration_sec"], 600.0, places=1)

    def test_segment_count_correct(self):
        result = validate_pacing(self._make_good_config())
        self.assertEqual(result["summary"]["segment_count"], 20)

    def test_strict_duration_fails_short(self):
        config = {"segments": _timeline(n=5, seg_dur=30.0)}  # 150s, way too short
        result = validate_pacing(config, strict_duration=True)
        self.assertFalse(result["ok"])
        self.assertTrue(any("DURATION_SHORT" in e for e in result["errors"]))

    def test_non_strict_duration_warns(self):
        config = {"segments": _timeline(n=5, seg_dur=30.0)}  # 150s
        result = validate_pacing(config, strict_duration=False)
        # Duration is a warning, not error
        self.assertTrue(any("DURATION_SHORT" in w for w in result["warnings"]))
        # But gaps and ordering may cause errors
        # Let's just check duration isn't in errors
        self.assertFalse(any("DURATION_SHORT" in e for e in result["errors"]))

    def test_empty_config_warns_not_fails(self):
        """Empty timeline with non-strict duration is a warning, not an error."""
        result = validate_pacing({}, strict_duration=False)
        self.assertTrue(result["ok"])  # No errors, just warnings
        self.assertTrue(any("EMPTY_TIMELINE" in w for w in result["warnings"]))

    def test_empty_config_strict_fails(self):
        result = validate_pacing({}, strict_duration=True)
        self.assertFalse(result["ok"])
        self.assertTrue(any("EMPTY_TIMELINE" in e for e in result["errors"]))

    def test_ordering_errors_detected(self):
        config = {"segments": [_seg(10, 5)]}  # Invalid ordering
        result = validate_pacing(config)
        self.assertFalse(result["ok"])
        self.assertTrue(any("INVALID_SEGMENT" in e for e in result["errors"]))

    def test_static_errors_detected(self):
        config = {"segments": [_seg(0, MAX_STATIC_SECONDS + 10)]}
        result = validate_pacing(config)
        self.assertFalse(result["ok"])
        self.assertTrue(any("LONG_STATIC" in e for e in result["errors"]))


if __name__ == "__main__":
    unittest.main()
