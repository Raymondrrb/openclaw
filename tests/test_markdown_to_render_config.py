#!/usr/bin/env python3
"""Tests for tools/markdown_to_render_config.py — Rayviews→RayVault converter."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from markdown_to_render_config import (
    NARRATION_TYPE_MAP,
    VARIANT_MAP,
    _image_for_kind,
    build_manifest,
    build_rayvault_products_json,
    build_rayvault_segments,
    build_render_config,
    build_segment_map,
    extract_script_text,
)


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

class TestConstants(unittest.TestCase):

    def test_variant_map_has_3_entries(self):
        self.assertEqual(len(VARIANT_MAP), 3)

    def test_variant_map_keys(self):
        self.assertIn("variant_01.png", VARIANT_MAP)
        self.assertIn("variant_02.png", VARIANT_MAP)
        self.assertIn("variant_03.png", VARIANT_MAP)

    def test_variant_map_values(self):
        self.assertEqual(VARIANT_MAP["variant_01.png"], "01_main.png")
        self.assertEqual(VARIANT_MAP["variant_02.png"], "02_glam.png")
        self.assertEqual(VARIANT_MAP["variant_03.png"], "03_broll.png")

    def test_narration_type_map_hook_is_intro(self):
        self.assertEqual(NARRATION_TYPE_MAP["hook"], "intro")

    def test_narration_type_map_outro(self):
        self.assertEqual(NARRATION_TYPE_MAP["outro"], "outro")

    def test_narration_type_map_winner_is_outro(self):
        self.assertEqual(NARRATION_TYPE_MAP["winner"], "outro")


# ---------------------------------------------------------------
# _image_for_kind
# ---------------------------------------------------------------

class TestImageForKind(unittest.TestCase):

    def test_avatar_talk(self):
        self.assertEqual(_image_for_kind("AVATAR_TALK"), "01_main.png")

    def test_product_glam(self):
        self.assertEqual(_image_for_kind("PRODUCT_GLAM"), "02_glam.png")

    def test_broll(self):
        self.assertEqual(_image_for_kind("BROLL"), "03_broll.png")

    def test_unknown_fallback(self):
        self.assertEqual(_image_for_kind("UNKNOWN"), "01_main.png")


# ---------------------------------------------------------------
# build_segment_map
# ---------------------------------------------------------------

class TestBuildSegmentMap(unittest.TestCase):

    def test_empty_timestamps(self):
        result = build_segment_map({})
        self.assertEqual(result, [])

    def test_empty_segments_list(self):
        result = build_segment_map({"segments": []})
        self.assertEqual(result, [])

    def test_hook_segment(self):
        ts = {"segments": [
            {"script_id": "hook", "start_ms": 0, "end_ms": 3000},
        ]}
        result = build_segment_map(ts)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["seg_type"], "intro")
        self.assertEqual(result[0]["start_ms"], 0)
        self.assertEqual(result[0]["end_ms"], 3000)

    def test_outro_segment(self):
        ts = {"segments": [
            {"script_id": "outro", "start_ms": 60000, "end_ms": 65000},
        ]}
        result = build_segment_map(ts)
        self.assertEqual(result[0]["seg_type"], "outro")

    def test_product_segment_parsed(self):
        ts = {"segments": [
            {"script_id": "p1_intro_AVATAR_TALK", "start_ms": 5000, "end_ms": 10000},
        ]}
        result = build_segment_map(ts)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["seg_type"], "product")
        self.assertEqual(result[0]["rank"], 1)
        self.assertEqual(result[0]["kind"], "AVATAR_TALK")

    def test_product_glam_segment(self):
        ts = {"segments": [
            {"script_id": "p3_intro_PRODUCT_GLAM", "start_ms": 20000, "end_ms": 25000},
        ]}
        result = build_segment_map(ts)
        self.assertEqual(result[0]["rank"], 3)
        self.assertEqual(result[0]["kind"], "PRODUCT_GLAM")

    def test_broll_segment(self):
        ts = {"segments": [
            {"script_id": "p2_intro_BROLL", "start_ms": 15000, "end_ms": 18000},
        ]}
        result = build_segment_map(ts)
        self.assertEqual(result[0]["kind"], "BROLL")
        self.assertEqual(result[0]["seg_type"], "product")

    def test_unknown_script_id_defaults_to_intro(self):
        ts = {"segments": [
            {"script_id": "some_unknown_id", "start_ms": 0, "end_ms": 1000},
        ]}
        result = build_segment_map(ts)
        self.assertEqual(result[0]["seg_type"], "intro")

    def test_winner_is_outro(self):
        ts = {"segments": [
            {"script_id": "winner", "start_ms": 50000, "end_ms": 55000},
        ]}
        result = build_segment_map(ts)
        self.assertEqual(result[0]["seg_type"], "outro")

    def test_multiple_segments_order(self):
        ts = {"segments": [
            {"script_id": "hook", "start_ms": 0, "end_ms": 3000},
            {"script_id": "p1_intro_AVATAR_TALK", "start_ms": 3000, "end_ms": 8000},
            {"script_id": "outro", "start_ms": 50000, "end_ms": 55000},
        ]}
        result = build_segment_map(ts)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["seg_type"], "intro")
        self.assertEqual(result[1]["seg_type"], "product")
        self.assertEqual(result[2]["seg_type"], "outro")


# ---------------------------------------------------------------
# build_rayvault_segments
# ---------------------------------------------------------------

class TestBuildRayvaultSegments(unittest.TestCase):

    def _make_seg_map(self):
        return [
            {"script_id": "hook", "start_ms": 0, "end_ms": 3000, "seg_type": "intro"},
            {"script_id": "p1_intro_AVATAR_TALK", "start_ms": 3000, "end_ms": 8000,
             "seg_type": "product", "rank": 1, "kind": "AVATAR_TALK"},
        ]

    def _make_products(self):
        return {"products": [
            {"rank": 1, "title": "Cool Widget Pro", "asin": "B0TEST1234"},
            {"rank": 2, "title": "Budget Widget", "asin": "B0TEST5678"},
        ]}

    def test_intro_segment_structure(self):
        seg_map = self._make_seg_map()[:1]
        result = build_rayvault_segments(seg_map, {}, self._make_products())
        self.assertEqual(len(result), 1)
        seg = result[0]
        self.assertEqual(seg["type"], "intro")
        self.assertEqual(seg["id"], "seg_000")
        self.assertEqual(seg["t0"], 0.0)
        self.assertEqual(seg["t1"], 3.0)

    def test_product_segment_with_image(self):
        seg_map = self._make_seg_map()[1:]
        product_images = {1: {"01_main.png": "products/p01/source_images/01_main.png"}}
        result = build_rayvault_segments(seg_map, product_images, self._make_products())
        seg = result[0]
        self.assertEqual(seg["type"], "product")
        self.assertEqual(seg["rank"], 1)
        self.assertEqual(seg["asin"], "B0TEST1234")
        self.assertEqual(seg["visual"]["mode"], "KEN_BURNS")
        self.assertIn("source", seg["visual"])

    def test_product_segment_without_image(self):
        seg_map = self._make_seg_map()[1:]
        result = build_rayvault_segments(seg_map, {}, self._make_products())
        seg = result[0]
        self.assertEqual(seg["visual"]["mode"], "SKIP")
        self.assertIsNone(seg["visual"]["source"])

    def test_frames_calculated(self):
        seg_map = [{"script_id": "hook", "start_ms": 0, "end_ms": 1000, "seg_type": "intro"}]
        result = build_rayvault_segments(seg_map, {}, {"products": []}, fps=30)
        self.assertEqual(result[0]["frames"], 30)

    def test_title_truncation(self):
        products = {"products": [
            {"rank": 1, "title": "A" * 100, "asin": "B0TEST1234"},
        ]}
        seg_map = [{"script_id": "p1_intro_AVATAR_TALK", "start_ms": 0, "end_ms": 5000,
                     "seg_type": "product", "rank": 1, "kind": "AVATAR_TALK"}]
        result = build_rayvault_segments(seg_map, {}, products)
        self.assertLessEqual(len(result[0]["title"]), 60)


# ---------------------------------------------------------------
# build_render_config
# ---------------------------------------------------------------

class TestBuildRenderConfig(unittest.TestCase):

    def test_basic_structure(self):
        segments = [
            {"type": "intro", "id": "seg_000", "t0": 0.0, "t1": 3.0, "frames": 90},
        ]
        config = build_render_config(segments, 60.0, {})
        self.assertEqual(config["version"], "1.3")
        self.assertIn("output", config)
        self.assertIn("canvas", config)
        self.assertIn("audio", config)
        self.assertIn("segments", config)
        self.assertIn("pacing", config)
        self.assertEqual(config["audio"]["duration_sec"], 60.0)

    def test_product_fidelity_score(self):
        segments = [
            {"type": "product", "rank": 1, "visual": {"mode": "KEN_BURNS"}},
            {"type": "product", "rank": 2, "visual": {"mode": "SKIP"}},
        ]
        config = build_render_config(segments, 30.0, {})
        self.assertEqual(config["products"]["truth_visuals_used"], 1)
        self.assertEqual(config["products"]["skipped_count"], 1)
        self.assertEqual(config["products"]["fidelity_score"], 50)

    def test_all_visuals_present(self):
        segments = [
            {"type": "product", "rank": 1, "visual": {"mode": "KEN_BURNS"}},
            {"type": "product", "rank": 2, "visual": {"mode": "KEN_BURNS"}},
        ]
        config = build_render_config(segments, 30.0, {})
        self.assertEqual(config["products"]["fidelity_score"], 100)

    def test_pacing_defaults(self):
        config = build_render_config([], 30.0, {})
        self.assertTrue(config["pacing"]["ok"])
        self.assertFalse(config["pacing"]["variety_warning"])
        self.assertEqual(config["pacing"]["errors"], [])


# ---------------------------------------------------------------
# build_manifest
# ---------------------------------------------------------------

class TestBuildManifest(unittest.TestCase):

    def test_ready_when_audio_available(self):
        products = {"products": [
            {"rank": 1, "asin": "B0ABC", "title": "Widget"},
        ]}
        m = build_manifest("run_001", Path("/tmp/test"), products, audio_available=True)
        self.assertEqual(m["status"], "READY_FOR_RENDER")

    def test_waiting_when_no_audio(self):
        products = {"products": []}
        m = build_manifest("run_001", Path("/tmp/test"), products, audio_available=False)
        self.assertEqual(m["status"], "WAITING_ASSETS")

    def test_product_list(self):
        products = {"products": [
            {"rank": 1, "asin": "B0ABC", "title": "Widget A"},
            {"rank": 2, "asin": "B0DEF", "title": "Widget B"},
        ]}
        m = build_manifest("run_001", Path("/tmp/test"), products, True)
        self.assertEqual(len(m["products"]), 2)
        self.assertEqual(m["products"][0]["rank"], 1)
        self.assertEqual(m["products"][0]["asin"], "B0ABC")

    def test_run_id_preserved(self):
        m = build_manifest("my_run_123", Path("/tmp/test"), {"products": []}, True)
        self.assertEqual(m["run_id"], "my_run_123")

    def test_version(self):
        m = build_manifest("r", Path("/tmp"), {"products": []}, True)
        self.assertEqual(m["version"], "1.3")

    def test_davinci_required(self):
        m = build_manifest("r", Path("/tmp"), {"products": []}, True)
        self.assertTrue(m["render"]["davinci_required"])


# ---------------------------------------------------------------
# extract_script_text
# ---------------------------------------------------------------

class TestExtractScriptText(unittest.TestCase):

    def test_empty_script(self):
        result = extract_script_text({})
        self.assertEqual(result, "")

    def test_empty_structure(self):
        result = extract_script_text({"structure": []})
        self.assertEqual(result, "")

    def test_single_segment_voice(self):
        script = {"structure": [
            {"voice_text": "Hello, welcome to the show."},
        ]}
        result = extract_script_text(script)
        self.assertEqual(result, "Hello, welcome to the show.")

    def test_nested_segments(self):
        script = {"structure": [
            {"voice_text": "Intro text.", "segments": [
                {"voice_text": "Product one is great."},
                {"voice_text": "Product two is decent."},
            ]},
        ]}
        result = extract_script_text(script)
        self.assertIn("Intro text.", result)
        self.assertIn("Product one is great.", result)
        self.assertIn("Product two is decent.", result)

    def test_skips_empty_voice_text(self):
        script = {"structure": [
            {"voice_text": ""},
            {"voice_text": "Only this."},
        ]}
        result = extract_script_text(script)
        self.assertEqual(result, "Only this.")

    def test_multiple_top_level_segments(self):
        script = {"structure": [
            {"voice_text": "First."},
            {"voice_text": "Second."},
        ]}
        result = extract_script_text(script)
        self.assertIn("First.", result)
        self.assertIn("Second.", result)
        self.assertIn("\n\n", result)


# ---------------------------------------------------------------
# build_rayvault_products_json
# ---------------------------------------------------------------

class TestBuildRayvaultProductsJson(unittest.TestCase):

    def test_empty_products(self):
        result = build_rayvault_products_json({"products": []}, {})
        self.assertEqual(result, {"items": []})

    def test_basic_product(self):
        products = {"products": [
            {"rank": 1, "asin": "B0ABC", "title": "Widget", "price": 29.99},
        ]}
        result = build_rayvault_products_json(products, {})
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["rank"], 1)
        self.assertEqual(item["asin"], "B0ABC")
        self.assertEqual(item["price"], 29.99)

    def test_includes_main_image_when_available(self):
        products = {"products": [
            {"rank": 1, "asin": "B0ABC", "title": "W", "price": 10},
        ]}
        images = {1: {"01_main.png": "products/p01/source_images/01_main.png"}}
        result = build_rayvault_products_json(products, images)
        self.assertEqual(result["items"][0]["main_image"], "products/p01/source_images/01_main.png")

    def test_no_main_image_key_when_missing(self):
        products = {"products": [
            {"rank": 1, "asin": "B0ABC", "title": "W", "price": 10},
        ]}
        result = build_rayvault_products_json(products, {})
        self.assertNotIn("main_image", result["items"][0])

    def test_title_truncation(self):
        products = {"products": [
            {"rank": 1, "asin": "B0ABC", "title": "X" * 100, "price": 10},
        ]}
        result = build_rayvault_products_json(products, {})
        self.assertLessEqual(len(result["items"][0]["title"]), 60)


if __name__ == "__main__":
    unittest.main()
