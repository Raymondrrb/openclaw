#!/usr/bin/env python3
"""Tests for rayvault/render_config_generate.py — timeline + visual mode resolution."""

from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from rayvault.policies import MAX_STATIC_SECONDS, MIN_SEGMENT_TYPE_VARIETY
from rayvault.render_config_generate import (
    CANVAS_DEFAULTS,
    RENDER_CONFIG_VERSION,
    T_INTRO,
    T_OUTRO,
    T_PER_PRODUCT_DEFAULT,
    T_PER_PRODUCT_MAX,
    T_PER_PRODUCT_MIN,
    clamp,
    estimate_duration_from_words,
    generate_timeline,
    validate_pacing,
    wav_duration_seconds,
)


# ---------------------------------------------------------------
# clamp
# ---------------------------------------------------------------

class TestClamp(unittest.TestCase):

    def test_in_range(self):
        self.assertEqual(clamp(5.0, 0.0, 10.0), 5.0)

    def test_below(self):
        self.assertEqual(clamp(-5.0, 0.0, 10.0), 0.0)

    def test_above(self):
        self.assertEqual(clamp(15.0, 0.0, 10.0), 10.0)

    def test_at_low(self):
        self.assertEqual(clamp(0.0, 0.0, 10.0), 0.0)

    def test_at_high(self):
        self.assertEqual(clamp(10.0, 0.0, 10.0), 10.0)


# ---------------------------------------------------------------
# wav_duration_seconds
# ---------------------------------------------------------------

class TestWavDurationSeconds(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_valid_wav(self):
        path = Path(self.tmpdir) / "test.wav"
        rate = 48000
        duration = 3.0
        n_samples = int(rate * duration)
        with wave.open(str(path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(b"\x00\x00" * n_samples)
        result = wav_duration_seconds(path)
        self.assertAlmostEqual(result, 3.0, places=1)

    def test_nonexistent_file(self):
        self.assertIsNone(wav_duration_seconds(Path("/nonexistent/audio.wav")))

    def test_invalid_file(self):
        path = Path(self.tmpdir) / "bad.wav"
        path.write_bytes(b"not a wav file")
        self.assertIsNone(wav_duration_seconds(path))


# ---------------------------------------------------------------
# estimate_duration_from_words
# ---------------------------------------------------------------

class TestEstimateDurationFromWords(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_150_words_is_60_sec(self):
        path = Path(self.tmpdir) / "script.txt"
        path.write_text(" ".join(["word"] * 150), encoding="utf-8")
        result = estimate_duration_from_words(path)
        self.assertAlmostEqual(result, 60.0, places=0)

    def test_min_10_seconds(self):
        path = Path(self.tmpdir) / "script.txt"
        path.write_text("hi", encoding="utf-8")
        result = estimate_duration_from_words(path)
        self.assertGreaterEqual(result, 10.0)

    def test_long_script(self):
        path = Path(self.tmpdir) / "script.txt"
        path.write_text(" ".join(["word"] * 1500), encoding="utf-8")
        result = estimate_duration_from_words(path)
        self.assertAlmostEqual(result, 600.0, places=0)


# ---------------------------------------------------------------
# generate_timeline
# ---------------------------------------------------------------

class TestGenerateTimeline(unittest.TestCase):

    def _make_visuals(self, n: int):
        return [
            {"rank": i + 1, "asin": f"B0{i:08d}", "title": f"Product {i+1}",
             "visual": {"mode": "KEN_BURNS", "source": f"p{i+1:02d}/01_main.jpg"}}
            for i in range(n)
        ]

    def test_has_intro_and_outro(self):
        segs = generate_timeline(self._make_visuals(3), 60.0)
        self.assertEqual(segs[0]["type"], "intro")
        self.assertEqual(segs[-1]["type"], "outro")

    def test_intro_duration(self):
        segs = generate_timeline(self._make_visuals(3), 60.0)
        intro = segs[0]
        self.assertAlmostEqual(intro["t1"] - intro["t0"], T_INTRO, places=2)

    def test_outro_duration(self):
        segs = generate_timeline(self._make_visuals(3), 60.0)
        outro = segs[-1]
        self.assertAlmostEqual(outro["t1"] - outro["t0"], T_OUTRO, places=2)

    def test_product_count(self):
        segs = generate_timeline(self._make_visuals(5), 60.0)
        product_segs = [s for s in segs if s["type"] == "product"]
        self.assertEqual(len(product_segs), 5)

    def test_total_segments(self):
        segs = generate_timeline(self._make_visuals(5), 60.0)
        self.assertEqual(len(segs), 7)  # 1 intro + 5 products + 1 outro

    def test_sequential_ids(self):
        segs = generate_timeline(self._make_visuals(3), 60.0)
        for i, seg in enumerate(segs):
            self.assertEqual(seg["id"], f"seg_{i:03d}")

    def test_monotonic_timing(self):
        segs = generate_timeline(self._make_visuals(5), 60.0)
        for i in range(1, len(segs)):
            self.assertGreaterEqual(segs[i]["t0"], segs[i-1]["t0"])
            self.assertAlmostEqual(segs[i]["t0"], segs[i-1]["t1"], places=2)

    def test_frames_positive(self):
        segs = generate_timeline(self._make_visuals(3), 60.0)
        for seg in segs:
            self.assertGreater(seg["frames"], 0)

    def test_per_product_clamped(self):
        segs = generate_timeline(self._make_visuals(5), 60.0)
        for seg in segs:
            if seg["type"] == "product":
                dur = seg["t1"] - seg["t0"]
                self.assertGreaterEqual(dur, T_PER_PRODUCT_MIN - 0.01)
                self.assertLessEqual(dur, T_PER_PRODUCT_MAX + 0.01)

    def test_empty_products(self):
        segs = generate_timeline([], 60.0)
        self.assertEqual(len(segs), 2)  # intro + outro

    def test_product_has_visual(self):
        segs = generate_timeline(self._make_visuals(1), 30.0)
        product = [s for s in segs if s["type"] == "product"][0]
        self.assertIn("visual", product)
        self.assertEqual(product["visual"]["mode"], "KEN_BURNS")

    def test_product_has_rank(self):
        segs = generate_timeline(self._make_visuals(3), 60.0)
        product = [s for s in segs if s["type"] == "product"][0]
        self.assertEqual(product["rank"], 1)


# ---------------------------------------------------------------
# validate_pacing (render_config_generate version)
# ---------------------------------------------------------------

class TestValidatePacing(unittest.TestCase):

    def _make_segments(self, n_products=5, mode="KEN_BURNS", duration=5.0):
        segs = [{"id": "seg_000", "type": "intro", "t0": 0, "t1": 2.0}]
        t = 2.0
        for i in range(n_products):
            segs.append({
                "id": f"seg_{i+1:03d}",
                "type": "product",
                "t0": t,
                "t1": t + duration,
                "visual": {"mode": mode},
            })
            t += duration
        segs.append({"id": f"seg_{n_products+1:03d}", "type": "outro", "t0": t, "t1": t + 1.5})
        return segs

    def test_valid_pacing(self):
        result = validate_pacing(self._make_segments())
        self.assertTrue(result["ok"])
        self.assertEqual(result["errors"], [])

    def test_long_static_fails(self):
        segs = self._make_segments(mode="STILL_ONLY", duration=MAX_STATIC_SECONDS + 5)
        result = validate_pacing(segs)
        self.assertFalse(result["ok"])
        self.assertTrue(any("LONG_STATIC" in e for e in result["errors"]))

    def test_ken_burns_exempt(self):
        segs = self._make_segments(mode="KEN_BURNS", duration=MAX_STATIC_SECONDS + 5)
        result = validate_pacing(segs)
        self.assertTrue(result["ok"])

    def test_broll_video_exempt(self):
        segs = self._make_segments(mode="BROLL_VIDEO", duration=MAX_STATIC_SECONDS + 5)
        result = validate_pacing(segs)
        self.assertTrue(result["ok"])

    def test_low_variety_warning(self):
        segs = self._make_segments(n_products=5, mode="KEN_BURNS")
        result = validate_pacing(segs)
        self.assertTrue(result["variety_warning"])
        self.assertTrue(any("LOW_VARIETY" in w for w in result["warnings"]))

    def test_varied_modes_no_warning(self):
        segs = self._make_segments()
        # Mix modes
        segs[1]["visual"]["mode"] = "KEN_BURNS"
        segs[2]["visual"]["mode"] = "BROLL_VIDEO"
        segs[3]["visual"]["mode"] = "STILL_ONLY"
        result = validate_pacing(segs)
        self.assertFalse(result["variety_warning"])

    def test_few_segments_no_variety_warning(self):
        segs = self._make_segments(n_products=1, mode="KEN_BURNS")
        result = validate_pacing(segs)
        # Only 3 segments total (intro, product, outro) — skip variety
        self.assertFalse(result["variety_warning"])


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

class TestRenderConfigConstants(unittest.TestCase):

    def test_version_string(self):
        self.assertIsInstance(RENDER_CONFIG_VERSION, str)

    def test_canvas_defaults(self):
        self.assertEqual(CANVAS_DEFAULTS["w"], 1920)
        self.assertEqual(CANVAS_DEFAULTS["h"], 1080)
        self.assertEqual(CANVAS_DEFAULTS["fps"], 30)

    def test_product_timing(self):
        self.assertLess(T_PER_PRODUCT_MIN, T_PER_PRODUCT_MAX)
        self.assertGreater(T_PER_PRODUCT_MIN, 0)


# ---------------------------------------------------------------
# clamp edge cases
# ---------------------------------------------------------------

class TestClampEdgeCases(unittest.TestCase):

    def test_equal_lo_hi(self):
        self.assertEqual(clamp(5.0, 3.0, 3.0), 3.0)

    def test_negative_range(self):
        self.assertEqual(clamp(-5.0, -10.0, -1.0), -5.0)

    def test_zero_range(self):
        self.assertEqual(clamp(0.0, 0.0, 0.0), 0.0)

    def test_integer_input(self):
        self.assertEqual(clamp(5, 0, 10), 5)

    def test_very_large_value(self):
        self.assertEqual(clamp(1e18, 0.0, 100.0), 100.0)


# ---------------------------------------------------------------
# generate_timeline edge cases
# ---------------------------------------------------------------

class TestGenerateTimelineEdgeCases(unittest.TestCase):

    def _make_visuals(self, n, mode="KEN_BURNS"):
        return [
            {"rank": i + 1, "asin": f"B0{i:08d}", "title": f"Product {i+1}",
             "visual": {"mode": mode, "source": f"p{i+1:02d}/01_main.jpg"}}
            for i in range(n)
        ]

    def test_single_product(self):
        segs = generate_timeline(self._make_visuals(1), 30.0)
        self.assertEqual(len(segs), 3)  # intro + 1 product + outro
        products = [s for s in segs if s["type"] == "product"]
        self.assertEqual(len(products), 1)

    def test_many_products_crowded(self):
        # 10 products in 30s of audio — per_product will be clamped to min
        segs = generate_timeline(self._make_visuals(10), 30.0)
        products = [s for s in segs if s["type"] == "product"]
        self.assertEqual(len(products), 10)
        for p in products:
            dur = p["t1"] - p["t0"]
            self.assertGreaterEqual(dur, T_PER_PRODUCT_MIN - 0.01)

    def test_very_short_audio(self):
        segs = generate_timeline(self._make_visuals(3), 5.0)
        # Should still produce all segments even with short audio
        self.assertEqual(len(segs), 5)

    def test_very_long_audio(self):
        # 600s audio, 5 products — per_product will be clamped to max
        segs = generate_timeline(self._make_visuals(5), 600.0)
        products = [s for s in segs if s["type"] == "product"]
        for p in products:
            dur = p["t1"] - p["t0"]
            self.assertLessEqual(dur, T_PER_PRODUCT_MAX + 0.01)

    def test_product_title_truncated(self):
        visuals = [{"rank": 1, "asin": "B0X", "title": "X" * 100,
                     "visual": {"mode": "KEN_BURNS"}}]
        segs = generate_timeline(visuals, 30.0)
        product = [s for s in segs if s["type"] == "product"][0]
        self.assertLessEqual(len(product["title"]), 60)

    def test_product_without_title(self):
        visuals = [{"rank": 1, "asin": "B0X",
                     "visual": {"mode": "KEN_BURNS"}}]
        segs = generate_timeline(visuals, 30.0)
        product = [s for s in segs if s["type"] == "product"][0]
        self.assertNotIn("title", product)

    def test_frames_match_fps(self):
        segs = generate_timeline(self._make_visuals(2), 30.0)
        fps = CANVAS_DEFAULTS["fps"]
        for seg in segs:
            expected_frames = round((seg["t1"] - seg["t0"]) * fps)
            self.assertEqual(seg["frames"], expected_frames)

    def test_segment_asin_preserved(self):
        segs = generate_timeline(self._make_visuals(2), 30.0)
        products = [s for s in segs if s["type"] == "product"]
        self.assertEqual(products[0]["asin"], "B000000000")
        self.assertEqual(products[1]["asin"], "B000000001")


# ---------------------------------------------------------------
# validate_pacing edge cases
# ---------------------------------------------------------------

class TestValidatePacingEdgeCases(unittest.TestCase):

    def test_empty_segments(self):
        result = validate_pacing([])
        self.assertTrue(result["ok"])
        self.assertEqual(result["errors"], [])

    def test_only_intro_outro(self):
        segs = [
            {"id": "seg_000", "type": "intro", "t0": 0, "t1": 2.0},
            {"id": "seg_001", "type": "outro", "t0": 2.0, "t1": 3.5},
        ]
        result = validate_pacing(segs)
        self.assertTrue(result["ok"])

    def test_skip_mode_long_duration(self):
        segs = [
            {"id": "seg_000", "type": "intro", "t0": 0, "t1": 2.0},
            {"id": "seg_001", "type": "product", "t0": 2.0, "t1": 2.0 + MAX_STATIC_SECONDS + 5,
             "visual": {"mode": "SKIP"}},
            {"id": "seg_002", "type": "product", "t0": 20.0, "t1": 25.0,
             "visual": {"mode": "KEN_BURNS"}},
            {"id": "seg_003", "type": "product", "t0": 25.0, "t1": 30.0,
             "visual": {"mode": "BROLL_VIDEO"}},
            {"id": "seg_004", "type": "outro", "t0": 30.0, "t1": 31.5},
        ]
        result = validate_pacing(segs)
        self.assertFalse(result["ok"])
        self.assertTrue(any("LONG_STATIC" in e for e in result["errors"]))

    def test_all_skip_low_variety(self):
        segs = [
            {"id": "seg_000", "type": "intro", "t0": 0, "t1": 2.0},
        ]
        for i in range(5):
            segs.append({
                "id": f"seg_{i+1:03d}", "type": "product",
                "t0": 2.0 + i*3, "t1": 5.0 + i*3,
                "visual": {"mode": "SKIP"},
            })
        segs.append({"id": "seg_006", "type": "outro", "t0": 17.0, "t1": 18.5})
        result = validate_pacing(segs)
        # All SKIP means no visual modes tracked
        self.assertTrue(result["variety_warning"])

    def test_missing_visual_key(self):
        segs = [
            {"id": "seg_000", "type": "intro", "t0": 0, "t1": 2.0},
            {"id": "seg_001", "type": "product", "t0": 2.0, "t1": 5.0},
            {"id": "seg_002", "type": "outro", "t0": 5.0, "t1": 6.5},
        ]
        # Should not crash if visual key is missing
        result = validate_pacing(segs)
        self.assertIsInstance(result["ok"], bool)


# ---------------------------------------------------------------
# estimate_duration_from_words edge cases
# ---------------------------------------------------------------

class TestEstimateDurationEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_file(self):
        path = Path(self.tmpdir) / "empty.txt"
        path.write_text("", encoding="utf-8")
        result = estimate_duration_from_words(path)
        self.assertGreaterEqual(result, 10.0)

    def test_single_word(self):
        path = Path(self.tmpdir) / "one.txt"
        path.write_text("hello", encoding="utf-8")
        result = estimate_duration_from_words(path)
        self.assertGreaterEqual(result, 10.0)

    def test_unicode_words(self):
        path = Path(self.tmpdir) / "unicode.txt"
        path.write_text("café résumé naïve " * 50, encoding="utf-8")
        result = estimate_duration_from_words(path)
        self.assertGreater(result, 10.0)


if __name__ == "__main__":
    unittest.main()
