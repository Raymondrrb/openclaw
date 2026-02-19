#!/usr/bin/env python3
"""Tests for rayvault/segment_id.py — immutable segment identifiers."""

from __future__ import annotations

import unittest

from rayvault.segment_id import (
    canonical_segment_dict,
    compute_segment_id,
    ensure_segment_ids,
    validate_segment_ids,
)


def _make_segment(**overrides) -> dict:
    """Build a base segment dict with optional overrides."""
    seg = {
        "type": "PRODUCT_INTRO",
        "role": "product",
        "asin": "B0ABC12345",
        "rank": 3,
        "start_sec": 60.0,
        "end_sec": 72.5,
        "visual": {"mode": "KEN_BURNS", "source": "hero_ref"},
        "motion": {"preset": "slow_zoom_in", "start_scale": 1.0, "end_scale": 1.15},
        "title": "Wireless Mouse Pro",
    }
    seg.update(overrides)
    return seg


class TestCanonicalSegmentDict(unittest.TestCase):

    def test_includes_core_identity(self):
        seg = _make_segment()
        canon = canonical_segment_dict(seg)
        self.assertEqual(canon["type"], "PRODUCT_INTRO")
        self.assertEqual(canon["role"], "product")
        self.assertEqual(canon["asin"], "B0ABC12345")
        self.assertEqual(canon["rank"], 3)

    def test_includes_visual(self):
        seg = _make_segment()
        canon = canonical_segment_dict(seg)
        self.assertEqual(canon["visual_mode"], "KEN_BURNS")
        self.assertEqual(canon["visual_source"], "hero_ref")

    def test_includes_motion(self):
        seg = _make_segment()
        canon = canonical_segment_dict(seg)
        self.assertEqual(canon["motion_preset"], "slow_zoom_in")
        self.assertAlmostEqual(canon["motion_start_scale"], 1.0)
        self.assertAlmostEqual(canon["motion_end_scale"], 1.15)

    def test_includes_title(self):
        seg = _make_segment()
        canon = canonical_segment_dict(seg)
        self.assertEqual(canon["title"], "Wireless Mouse Pro")

    def test_excludes_timing_fields(self):
        seg = _make_segment()
        canon = canonical_segment_dict(seg)
        self.assertNotIn("start_sec", canon)
        self.assertNotIn("end_sec", canon)

    def test_excludes_frames(self):
        seg = _make_segment(frames=1800)
        canon = canonical_segment_dict(seg)
        self.assertNotIn("frames", canon)

    def test_excludes_id_fields(self):
        seg = _make_segment(id="seg_001", segment_id="abc123")
        canon = canonical_segment_dict(seg)
        self.assertNotIn("id", canon)
        self.assertNotIn("segment_id", canon)

    def test_overlay_refs_sorted(self):
        seg = _make_segment(overlay_refs=[
            {"kind": "lower_third", "overlay_id": "lt_002"},
            {"kind": "price_tag", "overlay_id": "lt_001"},
        ])
        canon = canonical_segment_dict(seg)
        refs = canon["overlay_refs"]
        self.assertEqual(refs[0]["overlay_id"], "lt_001")
        self.assertEqual(refs[1]["overlay_id"], "lt_002")

    def test_empty_visual_excluded(self):
        seg = _make_segment(visual={})
        canon = canonical_segment_dict(seg)
        self.assertNotIn("visual_mode", canon)

    def test_empty_motion_excluded(self):
        seg = _make_segment(motion={})
        canon = canonical_segment_dict(seg)
        self.assertNotIn("motion_preset", canon)

    def test_no_overlay_refs(self):
        seg = _make_segment()
        canon = canonical_segment_dict(seg)
        self.assertNotIn("overlay_refs", canon)

    def test_missing_optional_keys(self):
        seg = {"type": "HOOK"}
        canon = canonical_segment_dict(seg)
        self.assertEqual(canon, {"type": "HOOK"})


class TestComputeSegmentId(unittest.TestCase):

    def test_returns_16_char_hex(self):
        seg = _make_segment()
        sid = compute_segment_id(seg)
        self.assertEqual(len(sid), 16)
        # Verify it's valid hex
        int(sid, 16)

    def test_deterministic(self):
        seg = _make_segment()
        id1 = compute_segment_id(seg)
        id2 = compute_segment_id(seg)
        self.assertEqual(id1, id2)

    def test_same_content_same_id(self):
        seg1 = _make_segment()
        seg2 = _make_segment()
        self.assertEqual(compute_segment_id(seg1), compute_segment_id(seg2))

    def test_timing_excluded(self):
        """Changing timing should NOT change the ID."""
        seg1 = _make_segment(start_sec=0.0, end_sec=10.0)
        seg2 = _make_segment(start_sec=60.0, end_sec=70.0)
        self.assertEqual(compute_segment_id(seg1), compute_segment_id(seg2))

    def test_different_type_different_id(self):
        seg1 = _make_segment(type="PRODUCT_INTRO")
        seg2 = _make_segment(type="PRODUCT_DEMO")
        self.assertNotEqual(compute_segment_id(seg1), compute_segment_id(seg2))

    def test_different_asin_different_id(self):
        seg1 = _make_segment(asin="B0ABC12345")
        seg2 = _make_segment(asin="B0XYZ67890")
        self.assertNotEqual(compute_segment_id(seg1), compute_segment_id(seg2))

    def test_different_rank_different_id(self):
        seg1 = _make_segment(rank=1)
        seg2 = _make_segment(rank=5)
        self.assertNotEqual(compute_segment_id(seg1), compute_segment_id(seg2))

    def test_different_motion_different_id(self):
        seg1 = _make_segment(motion={"preset": "slow_zoom_in", "start_scale": 1.0, "end_scale": 1.15})
        seg2 = _make_segment(motion={"preset": "slow_zoom_out", "start_scale": 1.15, "end_scale": 1.0})
        self.assertNotEqual(compute_segment_id(seg1), compute_segment_id(seg2))

    def test_different_title_different_id(self):
        seg1 = _make_segment(title="Product A")
        seg2 = _make_segment(title="Product B")
        self.assertNotEqual(compute_segment_id(seg1), compute_segment_id(seg2))

    def test_overlay_order_independent(self):
        """Overlay refs are sorted, so order shouldn't matter."""
        seg1 = _make_segment(overlay_refs=[
            {"kind": "a", "overlay_id": "001"},
            {"kind": "b", "overlay_id": "002"},
        ])
        seg2 = _make_segment(overlay_refs=[
            {"kind": "b", "overlay_id": "002"},
            {"kind": "a", "overlay_id": "001"},
        ])
        self.assertEqual(compute_segment_id(seg1), compute_segment_id(seg2))

    def test_minimal_segment(self):
        """Even a minimal segment should produce a valid ID."""
        sid = compute_segment_id({"type": "HOOK"})
        self.assertEqual(len(sid), 16)


class TestValidateSegmentIds(unittest.TestCase):

    def test_valid_ids_no_errors(self):
        seg = _make_segment()
        seg["segment_id"] = compute_segment_id(seg)
        errors = validate_segment_ids([seg])
        self.assertEqual(errors, [])

    def test_tampered_content_detected(self):
        seg = _make_segment()
        seg["segment_id"] = compute_segment_id(seg)
        seg["asin"] = "B0TAMPERED1"  # Tamper after computing ID
        errors = validate_segment_ids([seg])
        self.assertEqual(len(errors), 1)
        self.assertIn("SEGMENT_ID_MISMATCH", errors[0])

    def test_skips_without_segment_id(self):
        seg = _make_segment()  # No segment_id field
        errors = validate_segment_ids([seg])
        self.assertEqual(errors, [])

    def test_skips_old_id_field(self):
        seg = _make_segment(id="seg_001")  # Old-style ID, no segment_id
        errors = validate_segment_ids([seg])
        self.assertEqual(errors, [])

    def test_multiple_segments(self):
        segs = []
        for i in range(5):
            s = _make_segment(rank=i)
            s["segment_id"] = compute_segment_id(s)
            segs.append(s)
        errors = validate_segment_ids(segs)
        self.assertEqual(errors, [])

    def test_one_tampered_among_valid(self):
        segs = []
        for i in range(3):
            s = _make_segment(rank=i)
            s["segment_id"] = compute_segment_id(s)
            segs.append(s)
        segs[1]["rank"] = 99  # Tamper the second one
        errors = validate_segment_ids(segs)
        self.assertEqual(len(errors), 1)
        self.assertIn("index=1", errors[0])

    def test_empty_list(self):
        errors = validate_segment_ids([])
        self.assertEqual(errors, [])


class TestEnsureSegmentIds(unittest.TestCase):

    def test_adds_missing_ids(self):
        segs = [_make_segment(rank=i) for i in range(3)]
        result = ensure_segment_ids(segs)
        for seg in result:
            self.assertIn("segment_id", seg)
            self.assertEqual(len(seg["segment_id"]), 16)

    def test_preserves_existing_ids(self):
        seg = _make_segment()
        seg["segment_id"] = "custom_id_12345a"
        result = ensure_segment_ids([seg])
        self.assertEqual(result[0]["segment_id"], "custom_id_12345a")

    def test_modifies_in_place(self):
        segs = [_make_segment()]
        ensure_segment_ids(segs)
        self.assertIn("segment_id", segs[0])


if __name__ == "__main__":
    unittest.main()
