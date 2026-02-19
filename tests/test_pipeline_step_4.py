#!/usr/bin/env python3
"""Tests for pipeline_step_4_davinci_build.py — timeline plan and track mapping."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from pipeline_step_4_davinci_build import build_timeline_plan, TRACK_LAYOUT, PROJECT_SETTINGS


def _make_script() -> dict:
    return {
        "video_title": "Test Video",
        "segments": [
            {"type": "HOOK", "narration": "Here is what you need to know.", "visual_hint": "opening montage"},
            {"type": "CREDIBILITY", "narration": "I tested these for weeks.", "visual_hint": "test setup"},
            {"type": "PRODUCT_INTRO", "narration": "Number five.", "product_name": "Widget A", "visual_hint": "widget photo"},
            {"type": "PRODUCT_DEMO", "narration": "It works great for daily use.", "product_name": "Widget A", "visual_hint": "using widget"},
            {"type": "PRODUCT_REVIEW", "narration": "Build quality is solid.", "product_name": "Widget A", "visual_hint": "close-up"},
            {"type": "PRODUCT_RANK", "narration": "Get it if you need value.", "product_name": "Widget A"},
            {"type": "FORWARD_HOOK", "narration": "But wait."},
            {"type": "PRODUCT_INTRO", "narration": "Number four.", "product_name": "Widget B", "visual_hint": "widget b photo"},
            {"type": "PRODUCT_DEMO", "narration": "This one impressed me.", "product_name": "Widget B", "visual_hint": "demo b"},
            {"type": "PRODUCT_REVIEW", "narration": "Not perfect though.", "product_name": "Widget B", "visual_hint": "detail b"},
            {"type": "PRODUCT_RANK", "narration": "For power users only.", "product_name": "Widget B"},
            {"type": "WINNER_REINFORCEMENT", "narration": "Widget A wins.", "visual_hint": "comparison shot"},
            {"type": "ENDING_DECISION", "narration": "Check links below."},
        ],
        "youtube": {"description": "", "tags": [], "chapters": []},
    }


def _make_assets_manifest(with_images: bool = False, tmpdir: str = "") -> dict:
    products = [
        {
            "name": "Widget A",
            "images": [
                {"variant_id": "scene_02_v1", "path": f"{tmpdir}/img_a1.png", "exists": with_images, "segment_type": "PRODUCT_INTRO"},
                {"variant_id": "scene_02_v2", "path": f"{tmpdir}/img_a2.png", "exists": with_images, "segment_type": "PRODUCT_INTRO"},
            ],
            "status": "ready" if with_images else "pending",
        },
        {
            "name": "Widget B",
            "images": [
                {"variant_id": "scene_07_v1", "path": f"{tmpdir}/img_b1.png", "exists": with_images, "segment_type": "PRODUCT_INTRO"},
            ],
            "status": "ready" if with_images else "pending",
        },
    ]
    return {"products": products, "total_images": 3, "ready_images": 3 if with_images else 0}


def _make_voice_manifest(with_audio: bool = False) -> dict:
    segs = []
    for i, narration in enumerate([
        "Here is what you need to know.",
        "I tested these for weeks.",
        "Number five.",
        "It works great for daily use.",
        "Build quality is solid.",
        "Get it if you need value.",
        "But wait.",
        "Number four.",
        "This one impressed me.",
        "Not perfect though.",
        "For power users only.",
        "Widget A wins.",
        "Check links below.",
    ]):
        seg_type = ["HOOK", "CREDIBILITY", "PRODUCT_INTRO", "PRODUCT_DEMO", "PRODUCT_REVIEW",
                     "PRODUCT_RANK", "FORWARD_HOOK", "PRODUCT_INTRO", "PRODUCT_DEMO",
                     "PRODUCT_REVIEW", "PRODUCT_RANK", "WINNER_REINFORCEMENT", "ENDING_DECISION"][i]
        words = len(narration.split())
        segs.append({
            "segment_id": f"seg_{i:02d}_{seg_type.lower()}",
            "type": seg_type,
            "audio_file": f"/tmp/voice/seg_{i:02d}.wav",
            "audio_exists": with_audio,
            "estimated_seconds": round(words / 150 * 60, 1),
            "word_count": words,
        })
    return {
        "voice_name": "Thomas Louis",
        "voice_settings": {},
        "total_segments": len(segs),
        "segments": segs,
    }


class TestBuildTimelinePlan(unittest.TestCase):

    def test_returns_dict(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest())
        self.assertIsInstance(plan, dict)

    def test_has_required_keys(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest())
        for key in ("project_settings", "track_layout", "total_duration_seconds",
                     "total_segments", "audio_ready", "video_ready", "render_ready", "timeline"):
            self.assertIn(key, plan)

    def test_project_settings_included(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest())
        self.assertEqual(plan["project_settings"], PROJECT_SETTINGS)

    def test_track_layout_included(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest())
        self.assertEqual(plan["track_layout"], TRACK_LAYOUT)

    def test_segment_count_matches_script(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest())
        self.assertEqual(plan["total_segments"], 13)

    def test_total_duration_positive(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest())
        self.assertGreater(plan["total_duration_seconds"], 0)

    def test_cumulative_timing(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest())
        timeline = plan["timeline"]
        for i in range(1, len(timeline)):
            prev_end = timeline[i - 1]["end_seconds"]
            curr_start = timeline[i]["start_seconds"]
            self.assertAlmostEqual(prev_end, curr_start, places=1)

    def test_first_segment_starts_at_zero(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest())
        self.assertEqual(plan["timeline"][0]["start_seconds"], 0.0)

    def test_each_segment_has_a1_track(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest())
        for entry in plan["timeline"]:
            self.assertIn("A1", entry["tracks"])
            self.assertEqual(entry["tracks"]["A1"]["type"], "audio")

    def test_product_intro_has_v3_overlay(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest())
        intros = [e for e in plan["timeline"] if e["type"] == "PRODUCT_INTRO"]
        for intro in intros:
            self.assertIn("V3", intro["tracks"])
            self.assertEqual(intro["tracks"]["V3"]["type"], "text_overlay")

    def test_product_rank_has_v3_overlay(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest())
        ranks = [e for e in plan["timeline"] if e["type"] == "PRODUCT_RANK"]
        for rank in ranks:
            self.assertIn("V3", rank["tracks"])

    def test_winner_reinforcement_has_v3(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest())
        winners = [e for e in plan["timeline"] if e["type"] == "WINNER_REINFORCEMENT"]
        self.assertTrue(len(winners) > 0)
        self.assertIn("V3", winners[0]["tracks"])

    def test_audio_not_ready_without_files(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest(with_audio=False))
        self.assertFalse(plan["audio_ready"])

    def test_audio_ready_with_files(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest(with_audio=True))
        self.assertTrue(plan["audio_ready"])

    def test_video_not_ready_without_images(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(with_images=False), _make_voice_manifest())
        self.assertFalse(plan["video_ready"])

    def test_render_not_ready_with_unmatched_visual_hints(self):
        """Non-product visual hints (HOOK, CREDIBILITY) have no assets, so video stays not ready."""
        plan = build_timeline_plan(
            _make_script(),
            _make_assets_manifest(with_images=True),
            _make_voice_manifest(with_audio=True),
        )
        # HOOK/CREDIBILITY have visual_hints but no product images → video_ready=False
        self.assertFalse(plan["video_ready"])
        self.assertFalse(plan["render_ready"])

    def test_render_not_ready_when_audio_missing(self):
        plan = build_timeline_plan(
            _make_script(),
            _make_assets_manifest(with_images=True),
            _make_voice_manifest(with_audio=False),
        )
        self.assertFalse(plan["render_ready"])

    def test_v1_track_for_product_with_images(self):
        plan = build_timeline_plan(
            _make_script(),
            _make_assets_manifest(with_images=True),
            _make_voice_manifest(),
        )
        product_segs = [e for e in plan["timeline"] if e["product_name"] == "Widget A"]
        # At least some segments should have V1
        v1_segments = [e for e in product_segs if "V1" in e["tracks"]]
        self.assertGreater(len(v1_segments), 0)

    def test_v1_ready_true_with_images(self):
        plan = build_timeline_plan(
            _make_script(),
            _make_assets_manifest(with_images=True),
            _make_voice_manifest(),
        )
        product_segs = [e for e in plan["timeline"] if e["product_name"] == "Widget A" and "V1" in e["tracks"]]
        for seg in product_segs:
            self.assertTrue(seg["tracks"]["V1"]["ready"])

    def test_visual_hint_no_image_gets_placeholder(self):
        """Segments with visual_hint but no asset get V1 with ready=False."""
        plan = build_timeline_plan(
            _make_script(),
            _make_assets_manifest(with_images=False),
            _make_voice_manifest(),
        )
        hook = plan["timeline"][0]  # HOOK has visual_hint
        if "V1" in hook["tracks"]:
            self.assertFalse(hook["tracks"]["V1"]["ready"])

    def test_serializable(self):
        plan = build_timeline_plan(_make_script(), _make_assets_manifest(), _make_voice_manifest())
        serialized = json.dumps(plan)
        reparsed = json.loads(serialized)
        self.assertEqual(plan, reparsed)


# ---------------------------------------------------------------
# main() CLI tests
# ---------------------------------------------------------------

class TestMainCLI(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "run_001"
        self.run_dir.mkdir()
        (self.run_dir / "script.json").write_text(
            json.dumps(_make_script()), encoding="utf-8"
        )
        (self.run_dir / "assets_manifest.json").write_text(
            json.dumps(_make_assets_manifest()), encoding="utf-8"
        )
        (self.run_dir / "voice_manifest.json").write_text(
            json.dumps(_make_voice_manifest()), encoding="utf-8"
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_main(self):
        from pipeline_step_4_davinci_build import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            try:
                main()
            except SystemExit:
                pass

    def test_creates_timeline_plan(self):
        self._run_main()
        self.assertTrue((self.run_dir / "timeline_plan.json").exists())

    def test_timeline_plan_valid_json(self):
        self._run_main()
        data = json.loads((self.run_dir / "timeline_plan.json").read_text(encoding="utf-8"))
        self.assertIn("timeline", data)

    def test_no_render_flag_when_not_ready(self):
        self._run_main()
        self.assertFalse((self.run_dir / "render_ready.flag").exists())

    def test_no_render_flag_with_unmatched_visual_hints(self):
        """Script has non-product visual hints with no assets, so flag not created."""
        (self.run_dir / "assets_manifest.json").write_text(
            json.dumps(_make_assets_manifest(with_images=True)), encoding="utf-8"
        )
        (self.run_dir / "voice_manifest.json").write_text(
            json.dumps(_make_voice_manifest(with_audio=True)), encoding="utf-8"
        )
        self._run_main()
        self.assertFalse((self.run_dir / "render_ready.flag").exists())

    def test_skip_if_flag_exists(self):
        (self.run_dir / "render_ready.flag").write_text("ready", encoding="utf-8")
        from pipeline_step_4_davinci_build import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)

    def test_error_if_script_missing(self):
        (self.run_dir / "script.json").unlink()
        from pipeline_step_4_davinci_build import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_error_if_assets_missing(self):
        (self.run_dir / "assets_manifest.json").unlink()
        from pipeline_step_4_davinci_build import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_error_if_voice_missing(self):
        (self.run_dir / "voice_manifest.json").unlink()
        from pipeline_step_4_davinci_build import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
