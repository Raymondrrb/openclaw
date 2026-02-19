#!/usr/bin/env python3
"""Tests for tools/pipeline_step_2_generate_images.py — prompt generation + manifest."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from pipeline_step_2_generate_images import (
    build_assets_manifest,
    generate_dzine_prompts_from_scenes,
)


def _scene(hint="Product on desk", product="Widget", seg_type="PRODUCT_INTRO"):
    return {
        "visual_hint": hint,
        "product_name": product,
        "segment_type": seg_type,
    }


# ---------------------------------------------------------------
# generate_dzine_prompts_from_scenes
# ---------------------------------------------------------------

class TestGenerateDzinePrompts(unittest.TestCase):

    def test_empty_scenes(self):
        result = generate_dzine_prompts_from_scenes([], "Rayviews")
        self.assertEqual(result, [])

    def test_single_scene_returns_one_entry(self):
        scenes = [_scene()]
        result = generate_dzine_prompts_from_scenes(scenes, "Rayviews")
        self.assertEqual(len(result), 1)

    def test_three_variants_per_scene(self):
        scenes = [_scene()]
        result = generate_dzine_prompts_from_scenes(scenes, "Rayviews")
        self.assertEqual(len(result[0]["variants"]), 3)

    def test_variant_ids_sequential(self):
        scenes = [_scene(), _scene(product="Other")]
        result = generate_dzine_prompts_from_scenes(scenes, "Rayviews")
        self.assertEqual(result[0]["variants"][0]["id"], "scene_00_v1")
        self.assertEqual(result[0]["variants"][1]["id"], "scene_00_v2")
        self.assertEqual(result[0]["variants"][2]["id"], "scene_00_v3")
        self.assertEqual(result[1]["variants"][0]["id"], "scene_01_v1")

    def test_channel_name_in_prompt(self):
        scenes = [_scene()]
        result = generate_dzine_prompts_from_scenes(scenes, "TestChannel")
        prompt_text = result[0]["variants"][0]["prompt"]
        self.assertIn("TestChannel", prompt_text)

    def test_visual_hint_in_prompts(self):
        scenes = [_scene(hint="Close-up of headphone cushions")]
        result = generate_dzine_prompts_from_scenes(scenes, "Rayviews")
        for v in result[0]["variants"]:
            self.assertIn("headphone cushions", v["prompt"])

    def test_product_name_preserved(self):
        scenes = [_scene(product="Sony XM5")]
        result = generate_dzine_prompts_from_scenes(scenes, "Rayviews")
        self.assertEqual(result[0]["product_name"], "Sony XM5")

    def test_segment_type_preserved(self):
        scenes = [_scene(seg_type="PRODUCT_DEMO")]
        result = generate_dzine_prompts_from_scenes(scenes, "Rayviews")
        self.assertEqual(result[0]["segment_type"], "PRODUCT_DEMO")

    def test_model_name_in_prompts(self):
        scenes = [_scene()]
        result = generate_dzine_prompts_from_scenes(scenes, "Rayviews")
        for v in result[0]["variants"]:
            self.assertIn("NanoBanana Pro", v["prompt"])

    def test_no_text_in_image_directive(self):
        scenes = [_scene()]
        result = generate_dzine_prompts_from_scenes(scenes, "Rayviews")
        self.assertIn("No text in image", result[0]["variants"][0]["prompt"])

    def test_many_scenes(self):
        scenes = [_scene(product=f"P{i}") for i in range(20)]
        result = generate_dzine_prompts_from_scenes(scenes, "Rayviews")
        self.assertEqual(len(result), 20)
        self.assertEqual(result[19]["variants"][0]["id"], "scene_19_v1")


# ---------------------------------------------------------------
# build_assets_manifest
# ---------------------------------------------------------------

class TestBuildAssetsManifest(unittest.TestCase):

    def test_empty_prompts(self):
        with tempfile.TemporaryDirectory() as d:
            result = build_assets_manifest([], Path(d))
            self.assertEqual(result["total_images"], 0)
            self.assertEqual(result["ready_images"], 0)

    def test_pending_when_no_images_exist(self):
        prompts = generate_dzine_prompts_from_scenes([_scene()], "Rayviews")
        with tempfile.TemporaryDirectory() as d:
            result = build_assets_manifest(prompts, Path(d))
            self.assertEqual(result["total_images"], 3)
            self.assertEqual(result["ready_images"], 0)
            self.assertEqual(result["products"][0]["status"], "pending")

    def test_ready_when_all_images_exist(self):
        prompts = generate_dzine_prompts_from_scenes([_scene()], "Rayviews")
        with tempfile.TemporaryDirectory() as d:
            assets_dir = Path(d)
            # Create all 3 variant images
            for v in prompts[0]["variants"]:
                (assets_dir / f"{v['id']}.png").write_text("fake", encoding="utf-8")
            result = build_assets_manifest(prompts, assets_dir)
            self.assertEqual(result["ready_images"], 3)
            self.assertEqual(result["products"][0]["status"], "ready")

    def test_partial_images_stays_pending(self):
        prompts = generate_dzine_prompts_from_scenes([_scene()], "Rayviews")
        with tempfile.TemporaryDirectory() as d:
            assets_dir = Path(d)
            # Only create 1 of 3
            (assets_dir / "scene_00_v1.png").write_text("fake", encoding="utf-8")
            result = build_assets_manifest(prompts, assets_dir)
            self.assertEqual(result["ready_images"], 1)
            self.assertEqual(result["products"][0]["status"], "pending")

    def test_multiple_products_grouped(self):
        scenes = [
            _scene(product="Alpha"),
            _scene(product="Beta"),
            _scene(product="Alpha"),  # same product
        ]
        prompts = generate_dzine_prompts_from_scenes(scenes, "Rayviews")
        with tempfile.TemporaryDirectory() as d:
            result = build_assets_manifest(prompts, Path(d))
            names = [p["name"] for p in result["products"]]
            self.assertEqual(len(names), 2)
            self.assertIn("Alpha", names)
            self.assertIn("Beta", names)

    def test_empty_product_name_uses_scene_index(self):
        scene = {"visual_hint": "test", "product_name": "", "segment_type": "HOOK"}
        prompts = generate_dzine_prompts_from_scenes([scene], "Rayviews")
        with tempfile.TemporaryDirectory() as d:
            result = build_assets_manifest(prompts, Path(d))
            self.assertEqual(result["products"][0]["name"], "scene_00")

    def test_total_images_count(self):
        scenes = [_scene(product=f"P{i}") for i in range(4)]
        prompts = generate_dzine_prompts_from_scenes(scenes, "Rayviews")
        with tempfile.TemporaryDirectory() as d:
            result = build_assets_manifest(prompts, Path(d))
            self.assertEqual(result["total_images"], 12)  # 4 scenes × 3 variants


if __name__ == "__main__":
    unittest.main()
