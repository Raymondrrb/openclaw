#!/usr/bin/env python3
"""Tests for pipeline_step_2_generate_images.py — Dzine prompt generation and assets manifest."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from pipeline_step_2_generate_images import (
    build_assets_manifest,
    generate_dzine_prompts_from_scenes,
)


def _make_scenes(n: int = 3) -> list[dict]:
    scenes = []
    for i in range(n):
        scenes.append({
            "product_name": f"Product {i}" if i > 0 else "",
            "visual_hint": f"Scene {i} visual description",
            "segment_type": "PRODUCT_DEMO" if i > 0 else "HOOK",
        })
    return scenes


# ---------------------------------------------------------------
# generate_dzine_prompts_from_scenes
# ---------------------------------------------------------------

class TestGenerateDzinePrompts(unittest.TestCase):

    def test_returns_list(self):
        prompts = generate_dzine_prompts_from_scenes(_make_scenes(), "Rayviews")
        self.assertIsInstance(prompts, list)

    def test_correct_count(self):
        scenes = _make_scenes(5)
        prompts = generate_dzine_prompts_from_scenes(scenes, "Rayviews")
        self.assertEqual(len(prompts), 5)

    def test_each_has_3_variants(self):
        prompts = generate_dzine_prompts_from_scenes(_make_scenes(2), "Rayviews")
        for p in prompts:
            self.assertEqual(len(p["variants"]), 3)

    def test_variant_ids_format(self):
        prompts = generate_dzine_prompts_from_scenes(_make_scenes(2), "Rayviews")
        self.assertEqual(prompts[0]["variants"][0]["id"], "scene_00_v1")
        self.assertEqual(prompts[0]["variants"][1]["id"], "scene_00_v2")
        self.assertEqual(prompts[0]["variants"][2]["id"], "scene_00_v3")
        self.assertEqual(prompts[1]["variants"][0]["id"], "scene_01_v1")

    def test_scene_index_preserved(self):
        prompts = generate_dzine_prompts_from_scenes(_make_scenes(3), "Rayviews")
        for i, p in enumerate(prompts):
            self.assertEqual(p["scene_index"], i)

    def test_segment_type_preserved(self):
        prompts = generate_dzine_prompts_from_scenes(_make_scenes(), "Rayviews")
        self.assertEqual(prompts[0]["segment_type"], "HOOK")
        self.assertEqual(prompts[1]["segment_type"], "PRODUCT_DEMO")

    def test_product_name_preserved(self):
        prompts = generate_dzine_prompts_from_scenes(_make_scenes(), "Rayviews")
        self.assertEqual(prompts[0]["product_name"], "")
        self.assertEqual(prompts[1]["product_name"], "Product 1")

    def test_original_hint_preserved(self):
        prompts = generate_dzine_prompts_from_scenes(_make_scenes(), "Rayviews")
        self.assertEqual(prompts[0]["original_hint"], "Scene 0 visual description")

    def test_variant_prompt_contains_hint(self):
        prompts = generate_dzine_prompts_from_scenes(_make_scenes(1), "Rayviews")
        for v in prompts[0]["variants"]:
            self.assertIn("Scene 0 visual description", v["prompt"])

    def test_variant_model_is_nanobanana(self):
        prompts = generate_dzine_prompts_from_scenes(_make_scenes(1), "Rayviews")
        for v in prompts[0]["variants"]:
            self.assertEqual(v["model"], "NanoBanana Pro")

    def test_channel_name_in_prompt(self):
        prompts = generate_dzine_prompts_from_scenes(_make_scenes(1), "TestChannel")
        # Channel name appears in base_identity which is in v1 prompt
        self.assertIn("TestChannel", prompts[0]["variants"][0]["prompt"])

    def test_no_text_instruction_in_v1(self):
        prompts = generate_dzine_prompts_from_scenes(_make_scenes(1), "Rayviews")
        self.assertIn("No text in image", prompts[0]["variants"][0]["prompt"])

    def test_alternative_angle_in_v2(self):
        prompts = generate_dzine_prompts_from_scenes(_make_scenes(1), "Rayviews")
        self.assertIn("Alternative angle", prompts[0]["variants"][1]["prompt"])

    def test_closeup_in_v3(self):
        prompts = generate_dzine_prompts_from_scenes(_make_scenes(1), "Rayviews")
        self.assertIn("Close-up detail", prompts[0]["variants"][2]["prompt"])

    def test_empty_scenes(self):
        prompts = generate_dzine_prompts_from_scenes([], "Rayviews")
        self.assertEqual(prompts, [])

    def test_serializable(self):
        prompts = generate_dzine_prompts_from_scenes(_make_scenes(3), "Rayviews")
        serialized = json.dumps(prompts)
        self.assertEqual(json.loads(serialized), prompts)


# ---------------------------------------------------------------
# build_assets_manifest
# ---------------------------------------------------------------

class TestBuildAssetsManifest(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.assets_dir = Path(self.tmpdir) / "assets"
        self.assets_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_prompts(self, n: int = 2) -> list[dict]:
        prompts = []
        for i in range(n):
            prompts.append({
                "scene_index": i,
                "segment_type": "PRODUCT_DEMO",
                "product_name": f"Product {i}",
                "variants": [
                    {"id": f"scene_{i:02d}_v1"},
                    {"id": f"scene_{i:02d}_v2"},
                    {"id": f"scene_{i:02d}_v3"},
                ],
            })
        return prompts

    def test_returns_dict(self):
        manifest = build_assets_manifest(self._make_prompts(), self.assets_dir)
        self.assertIsInstance(manifest, dict)

    def test_has_products_key(self):
        manifest = build_assets_manifest(self._make_prompts(), self.assets_dir)
        self.assertIn("products", manifest)

    def test_total_images_count(self):
        manifest = build_assets_manifest(self._make_prompts(3), self.assets_dir)
        self.assertEqual(manifest["total_images"], 9)  # 3 products * 3 variants

    def test_ready_images_zero_when_none_exist(self):
        manifest = build_assets_manifest(self._make_prompts(), self.assets_dir)
        self.assertEqual(manifest["ready_images"], 0)

    def test_status_pending_when_no_images(self):
        manifest = build_assets_manifest(self._make_prompts(1), self.assets_dir)
        self.assertEqual(manifest["products"][0]["status"], "pending")

    def test_status_ready_when_all_images_exist(self):
        prompts = self._make_prompts(1)
        for v in prompts[0]["variants"]:
            (self.assets_dir / f"{v['id']}.png").write_bytes(b"\x89PNG")
        manifest = build_assets_manifest(prompts, self.assets_dir)
        self.assertEqual(manifest["products"][0]["status"], "ready")

    def test_status_pending_when_partial_images(self):
        prompts = self._make_prompts(1)
        (self.assets_dir / "scene_00_v1.png").write_bytes(b"\x89PNG")
        # Only 1 of 3 exists
        manifest = build_assets_manifest(prompts, self.assets_dir)
        self.assertEqual(manifest["products"][0]["status"], "pending")

    def test_ready_count_partial(self):
        prompts = self._make_prompts(1)
        (self.assets_dir / "scene_00_v1.png").write_bytes(b"\x89PNG")
        (self.assets_dir / "scene_00_v2.png").write_bytes(b"\x89PNG")
        manifest = build_assets_manifest(prompts, self.assets_dir)
        self.assertEqual(manifest["ready_images"], 2)

    def test_products_grouped_by_name(self):
        prompts = [
            {"scene_index": 0, "segment_type": "PRODUCT_INTRO", "product_name": "Mouse A",
             "variants": [{"id": "scene_00_v1"}]},
            {"scene_index": 1, "segment_type": "PRODUCT_DEMO", "product_name": "Mouse A",
             "variants": [{"id": "scene_01_v1"}]},
        ]
        manifest = build_assets_manifest(prompts, self.assets_dir)
        self.assertEqual(len(manifest["products"]), 1)
        self.assertEqual(manifest["products"][0]["name"], "Mouse A")
        self.assertEqual(len(manifest["products"][0]["images"]), 2)

    def test_empty_product_name_uses_scene_index(self):
        prompts = [
            {"scene_index": 0, "segment_type": "HOOK", "product_name": "",
             "variants": [{"id": "scene_00_v1"}]},
        ]
        manifest = build_assets_manifest(prompts, self.assets_dir)
        self.assertEqual(manifest["products"][0]["name"], "scene_00")

    def test_image_entries_have_required_fields(self):
        prompts = self._make_prompts(1)
        manifest = build_assets_manifest(prompts, self.assets_dir)
        img = manifest["products"][0]["images"][0]
        self.assertIn("variant_id", img)
        self.assertIn("path", img)
        self.assertIn("exists", img)
        self.assertIn("segment_type", img)

    def test_image_path_is_assets_dir_based(self):
        prompts = self._make_prompts(1)
        manifest = build_assets_manifest(prompts, self.assets_dir)
        img = manifest["products"][0]["images"][0]
        self.assertTrue(img["path"].startswith(str(self.assets_dir)))

    def test_empty_prompts(self):
        manifest = build_assets_manifest([], self.assets_dir)
        self.assertEqual(manifest["products"], [])
        self.assertEqual(manifest["total_images"], 0)
        self.assertEqual(manifest["ready_images"], 0)


# ---------------------------------------------------------------
# main() CLI tests
# ---------------------------------------------------------------

class TestMainCLI(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "run_001"
        self.run_dir.mkdir()
        # Write a valid script.json with visual_hint scenes
        script = {
            "video_title": "Test Video",
            "segments": [
                {"type": "HOOK", "narration": "Hello", "visual_hint": "opening scene"},
                {"type": "PRODUCT_INTRO", "narration": "Intro", "product_name": "Widget",
                 "visual_hint": "widget on desk"},
                {"type": "PRODUCT_DEMO", "narration": "Demo", "product_name": "Widget",
                 "visual_hint": "using widget"},
            ],
            "youtube": {"description": "Test", "tags": [], "chapters": []},
        }
        (self.run_dir / "script.json").write_text(json.dumps(script), encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_creates_prompts_and_manifest(self):
        from pipeline_step_2_generate_images import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            try:
                main()
            except SystemExit:
                pass
        self.assertTrue((self.run_dir / "dzine_prompts.json").exists())
        self.assertTrue((self.run_dir / "assets_manifest.json").exists())

    def test_prompts_json_valid(self):
        from pipeline_step_2_generate_images import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            try:
                main()
            except SystemExit:
                pass
        prompts = json.loads((self.run_dir / "dzine_prompts.json").read_text(encoding="utf-8"))
        self.assertIsInstance(prompts, list)
        self.assertEqual(len(prompts), 3)  # 3 scenes with visual_hint

    def test_manifest_json_valid(self):
        from pipeline_step_2_generate_images import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            try:
                main()
            except SystemExit:
                pass
        manifest = json.loads((self.run_dir / "assets_manifest.json").read_text(encoding="utf-8"))
        self.assertIn("products", manifest)
        self.assertIn("total_images", manifest)

    def test_skip_if_manifest_exists(self):
        (self.run_dir / "assets_manifest.json").write_text("{}", encoding="utf-8")
        from pipeline_step_2_generate_images import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)

    def test_error_if_no_script(self):
        (self.run_dir / "script.json").unlink()
        from pipeline_step_2_generate_images import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_assets_dir_created(self):
        from pipeline_step_2_generate_images import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            try:
                main()
            except SystemExit:
                pass
        self.assertTrue((self.run_dir / "assets").is_dir())

    def test_no_visual_hints_exits(self):
        script = {
            "video_title": "Test",
            "segments": [
                {"type": "HOOK", "narration": "No hints here"},
            ],
            "youtube": {"description": "", "tags": [], "chapters": []},
        }
        (self.run_dir / "script.json").write_text(json.dumps(script), encoding="utf-8")
        from pipeline_step_2_generate_images import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
