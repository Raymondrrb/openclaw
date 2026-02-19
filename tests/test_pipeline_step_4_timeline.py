#!/usr/bin/env python3
"""Tests for tools/pipeline_step_4_davinci_build.py — build_timeline_plan."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from pipeline_step_4_davinci_build import (
    TRACK_LAYOUT,
    PROJECT_SETTINGS,
    build_timeline_plan,
)


def _script(segments):
    return {"segments": segments}


def _seg(seg_type="HOOK", narration="Test narration here", product="", visual="hint"):
    d = {"type": seg_type, "narration": narration}
    if product:
        d["product_name"] = product
    if visual:
        d["visual_hint"] = visual
    return d


def _assets(products=None):
    return {"products": products or []}


def _voice(segments=None):
    return {"segments": segments or []}


def _voice_seg(seg_id, audio_file="audio.wav", exists=True, est_sec=3.0):
    return {
        "segment_id": seg_id,
        "audio_file": audio_file,
        "audio_exists": exists,
        "estimated_seconds": est_sec,
    }


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

class TestConstants(unittest.TestCase):

    def test_track_layout_has_expected_tracks(self):
        self.assertIn("V1", TRACK_LAYOUT)
        self.assertIn("V2", TRACK_LAYOUT)
        self.assertIn("V3", TRACK_LAYOUT)
        self.assertIn("A1", TRACK_LAYOUT)
        self.assertIn("A2", TRACK_LAYOUT)
        self.assertIn("A3", TRACK_LAYOUT)

    def test_project_settings_resolution(self):
        self.assertEqual(PROJECT_SETTINGS["resolution"], "1920x1080")
        self.assertEqual(PROJECT_SETTINGS["fps"], 30)


# ---------------------------------------------------------------
# build_timeline_plan
# ---------------------------------------------------------------

class TestBuildTimelinePlan(unittest.TestCase):

    def test_empty_script(self):
        result = build_timeline_plan(_script([]), _assets(), _voice())
        self.assertEqual(result["total_segments"], 0)
        self.assertEqual(result["total_duration_seconds"], 0)
        self.assertTrue(result["render_ready"])

    def test_single_segment_basic_structure(self):
        script = _script([_seg("HOOK", "Hello world")])
        result = build_timeline_plan(script, _assets(), _voice())
        self.assertEqual(result["total_segments"], 1)
        self.assertGreater(result["total_duration_seconds"], 0)
        self.assertIn("timeline", result)
        self.assertEqual(len(result["timeline"]), 1)

    def test_segment_has_timing(self):
        script = _script([_seg("HOOK", "One two three four five")])
        result = build_timeline_plan(script, _assets(), _voice())
        entry = result["timeline"][0]
        self.assertEqual(entry["start_seconds"], 0)
        self.assertGreater(entry["duration_seconds"], 0)
        self.assertEqual(entry["end_seconds"], entry["start_seconds"] + entry["duration_seconds"])

    def test_cumulative_timing(self):
        script = _script([
            _seg("HOOK", "Short hook sentence here"),
            _seg("CRITERIA", "Longer criteria description with many words in this segment"),
        ])
        result = build_timeline_plan(script, _assets(), _voice())
        self.assertEqual(result["timeline"][1]["start_seconds"],
                         result["timeline"][0]["end_seconds"])

    def test_audio_track_mapped(self):
        script = _script([_seg("HOOK", "Test audio")])
        voice = _voice([_voice_seg("seg_00_hook", "/tmp/hook.wav", True)])
        result = build_timeline_plan(script, _assets(), voice)
        a1 = result["timeline"][0]["tracks"]["A1"]
        self.assertEqual(a1["file"], "/tmp/hook.wav")
        self.assertTrue(a1["ready"])

    def test_audio_not_ready_when_missing(self):
        script = _script([_seg("HOOK", "Test audio")])
        result = build_timeline_plan(script, _assets(), _voice())
        a1 = result["timeline"][0]["tracks"]["A1"]
        self.assertFalse(a1["ready"])

    def test_video_track_from_assets(self):
        script = _script([_seg("PRODUCT_INTRO", "The Widget", product="Widget", visual="Product shot")])
        assets = _assets([{
            "name": "Widget",
            "images": [{"path": "/img/widget.png", "exists": True, "segment_type": "PRODUCT_INTRO"}],
            "status": "ready",
        }])
        result = build_timeline_plan(script, assets, _voice())
        v1 = result["timeline"][0]["tracks"]["V1"]
        self.assertEqual(v1["file"], "/img/widget.png")
        self.assertTrue(v1["ready"])

    def test_video_not_ready_note(self):
        script = _script([_seg("HOOK", "Visual segment", visual="Montage shot")])
        result = build_timeline_plan(script, _assets(), _voice())
        v1 = result["timeline"][0]["tracks"].get("V1", {})
        self.assertFalse(v1.get("ready", True))

    def test_text_overlay_for_product_intro(self):
        script = _script([_seg("PRODUCT_INTRO", "The Widget", product="Widget")])
        result = build_timeline_plan(script, _assets(), _voice())
        v3 = result["timeline"][0]["tracks"].get("V3", {})
        self.assertEqual(v3["type"], "text_overlay")
        self.assertEqual(v3["content"], "Widget")

    def test_text_overlay_for_product_rank(self):
        script = _script([_seg("PRODUCT_RANK", "Ranked here", product="Gizmo")])
        result = build_timeline_plan(script, _assets(), _voice())
        v3 = result["timeline"][0]["tracks"].get("V3", {})
        self.assertEqual(v3["content"], "Gizmo")

    def test_text_overlay_for_winner(self):
        script = _script([_seg("WINNER_REINFORCEMENT", "The best", product="Champ")])
        result = build_timeline_plan(script, _assets(), _voice())
        v3 = result["timeline"][0]["tracks"].get("V3", {})
        self.assertEqual(v3["content"], "Champ")

    def test_no_text_overlay_for_hook(self):
        script = _script([_seg("HOOK", "Opening hook")])
        result = build_timeline_plan(script, _assets(), _voice())
        self.assertNotIn("V3", result["timeline"][0]["tracks"])

    def test_render_ready_when_all_audio_ready(self):
        script = _script([_seg("HOOK", "Hello")])
        voice = _voice([_voice_seg("seg_00_hook", exists=True)])
        result = build_timeline_plan(script, _assets(), voice)
        self.assertTrue(result["audio_ready"])

    def test_render_not_ready_missing_audio(self):
        script = _script([_seg("HOOK", "Hello")])
        result = build_timeline_plan(script, _assets(), _voice())
        self.assertFalse(result["audio_ready"])
        self.assertFalse(result["render_ready"])

    def test_video_ready_when_no_visual_segments(self):
        script = _script([_seg("FORWARD_HOOK", "Next up", visual="")])
        voice = _voice([_voice_seg("seg_00_forward_hook", exists=True)])
        result = build_timeline_plan(script, _assets(), voice)
        self.assertTrue(result["video_ready"])

    def test_project_settings_included(self):
        result = build_timeline_plan(_script([]), _assets(), _voice())
        self.assertEqual(result["project_settings"]["fps"], 30)
        self.assertEqual(result["project_settings"]["resolution"], "1920x1080")

    def test_track_layout_included(self):
        result = build_timeline_plan(_script([]), _assets(), _voice())
        self.assertIn("V1", result["track_layout"])

    def test_total_duration_matches_sum(self):
        script = _script([
            _seg("HOOK", "One two three"),
            _seg("CRITERIA", "Four five six seven eight"),
            _seg("ENDING_DECISION", "Nine ten"),
        ])
        result = build_timeline_plan(script, _assets(), _voice())
        manual_sum = sum(t["duration_seconds"] for t in result["timeline"])
        self.assertAlmostEqual(result["total_duration_seconds"], round(manual_sum, 1), places=1)

    def test_full_pipeline_render_ready(self):
        script = _script([
            _seg("HOOK", "Opening hook sentence", visual="Montage"),
            _seg("PRODUCT_INTRO", "Product one", product="Prod1", visual="Product shot"),
        ])
        assets = _assets([{
            "name": "Prod1",
            "images": [{"path": "/img/p1.png", "exists": True, "segment_type": "PRODUCT_INTRO"}],
            "status": "ready",
        }])
        voice = _voice([
            _voice_seg("seg_00_hook", "/audio/hook.wav", True),
            _voice_seg("seg_01_product_intro", "/audio/intro.wav", True),
        ])
        result = build_timeline_plan(script, assets, voice)
        # V1 for hook has visual_hint but no assets → not ready
        self.assertFalse(result["video_ready"])
        self.assertTrue(result["audio_ready"])


# ---------------------------------------------------------------
# build_timeline_plan — edge cases
# ---------------------------------------------------------------

class TestBuildTimelinePlanEdgeCases(unittest.TestCase):

    def test_many_segments(self):
        segs = [_seg("PRODUCT_INTRO", f"Product {i} description", product=f"P{i}") for i in range(10)]
        result = build_timeline_plan(_script(segs), _assets(), _voice())
        self.assertEqual(result["total_segments"], 10)
        self.assertEqual(len(result["timeline"]), 10)

    def test_timing_never_negative(self):
        segs = [_seg("HOOK", "w " * 3), _seg("CRITERIA", "w " * 5)]
        result = build_timeline_plan(_script(segs), _assets(), _voice())
        for entry in result["timeline"]:
            self.assertGreaterEqual(entry["start_seconds"], 0)
            self.assertGreaterEqual(entry["duration_seconds"], 0)
            self.assertGreaterEqual(entry["end_seconds"], 0)

    def test_segment_type_preserved(self):
        script = _script([_seg("CRITERIA", "Selection criteria details")])
        result = build_timeline_plan(script, _assets(), _voice())
        self.assertEqual(result["timeline"][0]["type"], "CRITERIA")

    def test_timeline_entry_has_type(self):
        script = _script([_seg("HOOK", "Exact narration text here")])
        result = build_timeline_plan(script, _assets(), _voice())
        entry = result["timeline"][0]
        self.assertIn("type", entry)
        self.assertIn("tracks", entry)

    def test_multiple_products_audio_mapping(self):
        script = _script([
            _seg("PRODUCT_INTRO", "First product", product="A"),
            _seg("PRODUCT_INTRO", "Second product", product="B"),
        ])
        voice = _voice([
            _voice_seg("seg_00_product_intro", "/audio/a.wav", True),
            _voice_seg("seg_01_product_intro", "/audio/b.wav", True),
        ])
        result = build_timeline_plan(script, _assets(), voice)
        self.assertTrue(result["audio_ready"])

    def test_missing_visual_hint_no_crash(self):
        seg = {"type": "HOOK", "narration": "Test"}
        script = _script([seg])
        result = build_timeline_plan(script, _assets(), _voice())
        self.assertEqual(result["total_segments"], 1)

    def test_empty_narration(self):
        script = _script([_seg("HOOK", "")])
        result = build_timeline_plan(script, _assets(), _voice())
        self.assertEqual(result["total_segments"], 1)
        # Duration may be 0 for empty narration
        self.assertGreaterEqual(result["total_duration_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
