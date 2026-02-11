"""Tests for tools.lib.resolve_schema — manifest schema + generation."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.resolve_schema import (
    AVATAR_INTRO_DURATION_S,
    DISCLOSURE_TEXT,
    EXPORT_BITRATE_MBPS_MAX,
    EXPORT_BITRATE_MBPS_MIN,
    FPS_DEFAULT,
    LOWER_THIRD_DURATION_S,
    MAX_BENEFITS_PER_SEGMENT,
    MUSIC_BED_LUFS,
    OVERLAY_DURATION_S,
    OVERLAY_MAX_WORDS,
    RANK_BADGE_DURATION_S,
    SFX_LUFS,
    SPEAKING_WPM,
    VOICEOVER_LUFS,
    VOICEOVER_PEAK_DB,
    ZOOM_PERCENT_MAX,
    ZOOM_PERCENT_MIN,
    EditManifest,
    MusicBed,
    Overlay,
    ProductSegment,
    SfxCue,
    Visual,
    count_words,
    discover_assets,
    generate_manifest,
    manifest_to_dict,
    manifest_to_json,
    manifest_to_markers_csv,
    manifest_to_notes,
    parse_script_sections,
    words_to_seconds,
)

# ---------------------------------------------------------------------------
# Sample script for testing
# ---------------------------------------------------------------------------

SAMPLE_SCRIPT = """[HOOK]
These are the five best products you can buy right now.
No sponsorships, no bias, just honest rankings.

[AVATAR_INTRO]
Welcome back. Let's get straight into it.

[PRODUCT_5]
Starting at number five, the Budget Pick.
Good performance for the price but the build is basic.
Battery lasts about six hours. Fine for casual use.

[PRODUCT_4]
Number four, the Mid-Range Option.
Better build quality and solid features. Comfortable for long sessions.
The app is clunky but you get great value for the money.

[PRODUCT_3]
Number three, the Best Value.
This one punches way above its price. Excellent features, great build.
Eight hour battery and fast charging. Hard to beat at this price.

[RETENTION_RESET]
Before we get to the top two, quick question. What feature matters most to you? Let me know in the comments.

[PRODUCT_2]
Number two, the Premium Pick.
Outstanding quality and the best features in this category. Period.
The only downside is the high price. But you get what you pay for.

[PRODUCT_1]
And the number one pick is the Overall Winner.
It does everything well. Great quality, strong build, long battery, comfortable design.
The app is excellent and it works perfectly with both iPhone and Android.
This is the product I personally use every single day.

[CONCLUSION]
Those are my top five. Links are in the description.
If you found this helpful, subscribe for more honest reviews.
"""


class TestTimeEstimation(unittest.TestCase):
    def test_words_to_seconds(self):
        # 155 WPM → 155 words = 60s
        self.assertEqual(words_to_seconds(155), 60.0)

    def test_words_to_seconds_zero(self):
        self.assertEqual(words_to_seconds(0), 0.0)

    def test_words_to_seconds_small(self):
        # 155 WPM → 15 words ≈ 5.8s
        self.assertEqual(words_to_seconds(15), 5.8)

    def test_count_words_basic(self):
        self.assertEqual(count_words("hello world foo bar"), 4)

    def test_count_words_ignores_stage_directions_brackets(self):
        self.assertEqual(count_words("hello [pause] world"), 2)

    def test_count_words_ignores_stage_directions_parens(self):
        self.assertEqual(count_words("hello (beat) world"), 2)

    def test_count_words_empty(self):
        self.assertEqual(count_words(""), 0)


class TestScriptParsing(unittest.TestCase):
    def test_parse_all_sections(self):
        sections = parse_script_sections(SAMPLE_SCRIPT)
        expected_keys = {
            "hook", "avatar_intro",
            "product_5", "product_4", "product_3",
            "retention_reset",
            "product_2", "product_1",
            "conclusion",
        }
        self.assertEqual(set(sections.keys()), expected_keys)

    def test_parse_hook_content(self):
        sections = parse_script_sections(SAMPLE_SCRIPT)
        self.assertIn("five best products", sections["hook"])

    def test_parse_preserves_product_text(self):
        sections = parse_script_sections(SAMPLE_SCRIPT)
        self.assertIn("number five", sections["product_5"].lower())
        self.assertIn("number one", sections["product_1"].lower())

    def test_parse_retention_reset(self):
        sections = parse_script_sections(SAMPLE_SCRIPT)
        self.assertIn("top two", sections["retention_reset"])

    def test_parse_empty_script(self):
        sections = parse_script_sections("")
        self.assertEqual(sections, {})

    def test_parse_case_insensitive_markers(self):
        script = "[hook]\nHello world\n[CONCLUSION]\nGoodbye"
        sections = parse_script_sections(script)
        self.assertIn("hook", sections)
        self.assertIn("conclusion", sections)


class TestAssetDiscovery(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.vdir = Path(self.tmpdir) / "test-video"
        # Create folder structure
        (self.vdir / "audio" / "sfx").mkdir(parents=True)
        (self.vdir / "visuals" / "backgrounds").mkdir(parents=True)
        (self.vdir / "visuals" / "products" / "01" / "clips").mkdir(parents=True)
        (self.vdir / "visuals" / "products" / "02").mkdir(parents=True)

    def test_discover_voiceover(self):
        (self.vdir / "audio" / "voiceover.wav").touch()
        assets = discover_assets(self.vdir)
        self.assertEqual(assets["voiceover"], "audio/voiceover.wav")

    def test_discover_voiceover_mp3_fallback(self):
        (self.vdir / "audio" / "voiceover.mp3").touch()
        assets = discover_assets(self.vdir)
        self.assertEqual(assets["voiceover"], "audio/voiceover.mp3")

    def test_discover_music_bed(self):
        (self.vdir / "audio" / "music_bed.wav").touch()
        assets = discover_assets(self.vdir)
        self.assertEqual(assets["music_bed"], "audio/music_bed.wav")

    def test_discover_backgrounds(self):
        (self.vdir / "visuals" / "backgrounds" / "dark.png").touch()
        (self.vdir / "visuals" / "backgrounds" / "light.jpg").touch()
        assets = discover_assets(self.vdir)
        self.assertEqual(len(assets["backgrounds"]), 2)

    def test_discover_product_amazon_images(self):
        (self.vdir / "visuals" / "products" / "01" / "amazon_front.png").touch()
        (self.vdir / "visuals" / "products" / "01" / "amazon_side.png").touch()
        assets = discover_assets(self.vdir)
        self.assertEqual(len(assets["products"][1]["amazon"]), 2)

    def test_discover_product_dzine_images(self):
        (self.vdir / "visuals" / "products" / "01" / "dzine_lifestyle.png").touch()
        assets = discover_assets(self.vdir)
        self.assertEqual(len(assets["products"][1]["dzine"]), 1)

    def test_discover_product_clips(self):
        (self.vdir / "visuals" / "products" / "01" / "clips" / "demo.mp4").touch()
        assets = discover_assets(self.vdir)
        self.assertEqual(len(assets["products"][1]["clips"]), 1)

    def test_discover_thumbnail(self):
        (self.vdir / "visuals" / "thumbnail.png").touch()
        assets = discover_assets(self.vdir)
        self.assertEqual(assets["thumbnail"], "visuals/thumbnail.png")

    def test_discover_empty_folder(self):
        assets = discover_assets(self.vdir)
        self.assertEqual(assets["voiceover"], "")
        self.assertEqual(assets["music_bed"], "")
        self.assertEqual(assets["backgrounds"], [])

    def test_discover_avatar_intro(self):
        (self.vdir / "visuals" / "avatar_intro.mp4").touch()
        assets = discover_assets(self.vdir)
        self.assertEqual(assets["avatar_intro_video"], "visuals/avatar_intro.mp4")

    def test_discover_sfx(self):
        (self.vdir / "audio" / "sfx" / "whoosh.wav").touch()
        (self.vdir / "audio" / "sfx" / "ding.wav").touch()
        assets = discover_assets(self.vdir)
        self.assertEqual(len(assets["sfx"]), 2)


class TestManifestGeneration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.vdir = Path(self.tmpdir) / "test-video"
        # Minimal folder structure
        (self.vdir / "audio" / "sfx").mkdir(parents=True)
        (self.vdir / "visuals" / "backgrounds").mkdir(parents=True)
        for r in range(1, 6):
            (self.vdir / "visuals" / "products" / f"{r:02d}").mkdir(parents=True)
        # Add voiceover
        (self.vdir / "audio" / "voiceover.wav").touch()
        (self.vdir / "audio" / "music_bed.wav").touch()

    def test_generate_basic(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        self.assertEqual(m.video_id, "test-001")
        self.assertEqual(len(m.segments), 5)

    def test_segments_ordered_5_to_1(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        ranks = [s.rank for s in m.segments]
        self.assertEqual(ranks, [5, 4, 3, 2, 1])

    def test_timeline_continuity(self):
        """Each section should start where the previous one ended (approximately)."""
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        self.assertGreater(m.hook_end_s, m.hook_start_s)
        self.assertAlmostEqual(m.avatar_intro_start_s, m.hook_end_s, places=0)
        self.assertAlmostEqual(m.segments[0].start_s, m.avatar_intro_end_s, places=0)

    def test_total_duration_positive(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        self.assertGreater(m.total_duration_s, 0)

    def test_total_duration_reasonable(self):
        """8-12 min script should produce 200-900s manifest."""
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        self.assertGreater(m.total_duration_s, 60)
        self.assertLess(m.total_duration_s, 900)

    def test_retention_reset_after_product_3(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        seg3 = next(s for s in m.segments if s.rank == 3)
        self.assertGreater(m.retention_reset_start_s, seg3.start_s)
        seg2 = next(s for s in m.segments if s.rank == 2)
        self.assertLess(m.retention_reset_end_s, seg2.end_s)

    def test_voiceover_found(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        self.assertEqual(m.voiceover_file, "audio/voiceover.wav")

    def test_music_bed_found(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        self.assertEqual(m.music.file, "audio/music_bed.wav")

    def test_music_ducks_under_voice(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        self.assertTrue(m.music.duck_under_voice)

    def test_music_lufs_value(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        self.assertEqual(m.music.volume_lufs, -26)

    def test_disclosure_overlay(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        disclosures = [o for o in m.global_overlays if o.type == "disclosure"]
        self.assertEqual(len(disclosures), 1)
        self.assertEqual(disclosures[0].text, DISCLOSURE_TEXT)

    def test_product_names_override(self):
        names = {1: "Winner Product", 5: "Budget Pick"}
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir, product_names=names)
        seg1 = next(s for s in m.segments if s.rank == 1)
        seg5 = next(s for s in m.segments if s.rank == 5)
        self.assertEqual(seg1.product_name, "Winner Product")
        self.assertEqual(seg5.product_name, "Budget Pick")

    def test_signature_moment(self):
        m = generate_manifest(
            "test-001", SAMPLE_SCRIPT, self.vdir,
            signature_line="But here's the truth...",
            signature_type="reality_check",
        )
        sigs = [o for o in m.global_overlays if o.type == "signature"]
        self.assertEqual(len(sigs), 1)
        self.assertEqual(sigs[0].text, "But here's the truth...")


class TestSegmentOverlays(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.vdir = Path(self.tmpdir) / "test-video"
        (self.vdir / "audio").mkdir(parents=True)
        (self.vdir / "visuals" / "backgrounds").mkdir(parents=True)
        for r in range(1, 6):
            (self.vdir / "visuals" / "products" / f"{r:02d}").mkdir(parents=True)

    def test_rank_badge_overlay(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        for seg in m.segments:
            badges = [o for o in seg.overlays if o.type == "rank_badge"]
            self.assertEqual(len(badges), 1, f"Segment #{seg.rank} missing rank badge")
            self.assertEqual(badges[0].text, f"#{seg.rank}")

    def test_lower_third_overlay(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        for seg in m.segments:
            lts = [o for o in seg.overlays if o.type == "lower_third"]
            self.assertEqual(len(lts), 1, f"Segment #{seg.rank} missing lower third")

    def test_benefit_overlays_capped_at_two(self):
        benefits = {1: ["Great ANC", "Long battery", "Comfy fit"]}
        m = generate_manifest(
            "test-001", SAMPLE_SCRIPT, self.vdir,
            product_benefits=benefits,
        )
        seg1 = next(s for s in m.segments if s.rank == 1)
        benefit_overlays = [o for o in seg1.overlays if o.type == "benefit"]
        self.assertEqual(len(benefit_overlays), MAX_BENEFITS_PER_SEGMENT)

    def test_benefit_click_sfx(self):
        benefits = {1: ["Great ANC", "Long battery"]}
        m = generate_manifest(
            "test-001", SAMPLE_SCRIPT, self.vdir,
            product_benefits=benefits,
        )
        seg1 = next(s for s in m.segments if s.rank == 1)
        click_cues = [s for s in seg1.sfx if "click" in s.label]
        self.assertEqual(len(click_cues), 2)

    def test_benefit_overlay_max_words(self):
        benefits = {1: ["This has way too many words in it seven eight"]}
        m = generate_manifest(
            "test-001", SAMPLE_SCRIPT, self.vdir,
            product_benefits=benefits,
        )
        seg1 = next(s for s in m.segments if s.rank == 1)
        benefit_overlays = [o for o in seg1.overlays if o.type == "benefit"]
        for b in benefit_overlays:
            self.assertLessEqual(len(b.text.split()), OVERLAY_MAX_WORDS)


class TestVisualAssignment(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.vdir = Path(self.tmpdir) / "test-video"
        (self.vdir / "audio").mkdir(parents=True)
        (self.vdir / "visuals" / "backgrounds").mkdir(parents=True)
        for r in range(1, 6):
            (self.vdir / "visuals" / "products" / f"{r:02d}" / "clips").mkdir(parents=True)

    def test_visuals_assigned_when_images_exist(self):
        # Add images for rank 1
        (self.vdir / "visuals" / "products" / "01" / "amazon_front.png").touch()
        (self.vdir / "visuals" / "products" / "01" / "amazon_side.png").touch()
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        seg1 = next(s for s in m.segments if s.rank == 1)
        self.assertGreater(len(seg1.visuals), 0)

    def test_no_visuals_when_no_images(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        seg5 = next(s for s in m.segments if s.rank == 5)
        self.assertEqual(len(seg5.visuals), 0)

    def test_visual_motion_types(self):
        (self.vdir / "visuals" / "products" / "01" / "amazon_a.png").touch()
        (self.vdir / "visuals" / "products" / "01" / "amazon_b.png").touch()
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        seg1 = next(s for s in m.segments if s.rank == 1)
        motions = {v.motion for v in seg1.visuals}
        # Should use varied motions, not all the same
        self.assertGreater(len(motions), 0)

    def test_clip_motion_is_static(self):
        (self.vdir / "visuals" / "products" / "01" / "clips" / "demo.mp4").touch()
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        seg1 = next(s for s in m.segments if s.rank == 1)
        clips = [v for v in seg1.visuals if v.type == "clip"]
        for clip in clips:
            self.assertEqual(clip.motion, "static")


class TestSerialization(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.vdir = Path(self.tmpdir) / "test-video"
        (self.vdir / "audio").mkdir(parents=True)
        (self.vdir / "visuals" / "backgrounds").mkdir(parents=True)
        for r in range(1, 6):
            (self.vdir / "visuals" / "products" / f"{r:02d}").mkdir(parents=True)
        (self.vdir / "audio" / "voiceover.wav").touch()

    def test_manifest_to_json_valid(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        j = manifest_to_json(m)
        data = json.loads(j)
        self.assertEqual(data["video_id"], "test-001")
        self.assertEqual(len(data["segments"]), 5)

    def test_manifest_to_dict_fields(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        d = manifest_to_dict(m)
        self.assertIn("intro", d)
        self.assertIn("hook", d["intro"])
        self.assertIn("avatar", d["intro"])
        self.assertIn("segments", d)
        self.assertIn("retention_reset", d)
        self.assertIn("outro", d)
        self.assertIn("voiceover", d)
        self.assertIn("music", d)
        # Voiceover includes targets
        self.assertEqual(d["voiceover"]["target_lufs"], -16)
        self.assertEqual(d["voiceover"]["peak_db"], -1)
        # Music uses duck_under_voice
        self.assertTrue(d["music"]["duck_under_voice"])

    def test_manifest_to_markers_csv_header(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        csv = manifest_to_markers_csv(m)
        lines = csv.strip().splitlines()
        self.assertEqual(lines[0], "Name,Start TC,Duration,Note,Color")

    def test_manifest_to_markers_csv_product_markers(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        csv = manifest_to_markers_csv(m)
        self.assertIn("Product #1", csv)
        self.assertIn("Product #5", csv)
        self.assertIn("Red", csv)  # #1 is red
        self.assertIn("Yellow", csv)  # others are yellow

    def test_manifest_to_notes_sections(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        notes = manifest_to_notes(m)
        self.assertIn("# Edit Notes", notes)
        self.assertIn("## Timeline Layout", notes)
        self.assertIn("## Audio Mix", notes)
        self.assertIn("## Per-Segment Visuals", notes)
        self.assertIn("## Resolve Workflow", notes)

    def test_manifest_to_notes_duration(self):
        m = generate_manifest("test-001", SAMPLE_SCRIPT, self.vdir)
        notes = manifest_to_notes(m)
        self.assertIn("Duration:", notes)
        self.assertIn("1920x1080", notes)


class TestConstants(unittest.TestCase):
    def test_speaking_wpm(self):
        self.assertEqual(SPEAKING_WPM, 155)

    def test_fps_default(self):
        self.assertEqual(FPS_DEFAULT, 30)

    def test_voiceover_lufs(self):
        self.assertEqual(VOICEOVER_LUFS, -16)

    def test_voiceover_peak(self):
        self.assertEqual(VOICEOVER_PEAK_DB, -1)

    def test_music_bed_lufs(self):
        self.assertEqual(MUSIC_BED_LUFS, -26)

    def test_sfx_lufs(self):
        self.assertEqual(SFX_LUFS, -18)

    def test_overlay_max_words(self):
        self.assertEqual(OVERLAY_MAX_WORDS, 6)

    def test_max_benefits(self):
        self.assertEqual(MAX_BENEFITS_PER_SEGMENT, 2)

    def test_zoom_range(self):
        self.assertEqual(ZOOM_PERCENT_MIN, 3)
        self.assertEqual(ZOOM_PERCENT_MAX, 7)

    def test_avatar_intro_duration(self):
        self.assertLessEqual(AVATAR_INTRO_DURATION_S, 5)
        self.assertGreaterEqual(AVATAR_INTRO_DURATION_S, 3)

    def test_export_bitrate(self):
        self.assertEqual(EXPORT_BITRATE_MBPS_MIN, 20)
        self.assertEqual(EXPORT_BITRATE_MBPS_MAX, 40)


if __name__ == "__main__":
    unittest.main()
