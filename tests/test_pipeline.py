"""Tests for tools/pipeline.py and tools/lib/video_paths.py.

Covers: VideoPaths, init, research, script, status subcommands.
No browser/API calls — mocks dzine_browser and tts_generate where needed.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.video_paths import VideoPaths


class TestVideoPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Patch VIDEOS_BASE so we use the temp dir
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", Path(self.tmp.name))
        self.patcher.start()
        self.paths = VideoPaths("test-001")

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_root_path(self):
        self.assertTrue(str(self.paths.root).endswith("test-001"))

    def test_products_json_path(self):
        self.assertEqual(
            self.paths.products_json,
            self.paths.root / "inputs" / "products.json",
        )

    def test_niche_txt_path(self):
        self.assertEqual(
            self.paths.niche_txt,
            self.paths.root / "inputs" / "niche.txt",
        )

    def test_script_txt_path(self):
        self.assertEqual(
            self.paths.script_txt,
            self.paths.root / "script" / "script.txt",
        )

    def test_thumbnail_path(self):
        self.assertEqual(
            self.paths.thumbnail_path(),
            self.paths.root / "assets" / "dzine" / "thumbnail.png",
        )

    def test_product_image_path(self):
        self.assertEqual(
            self.paths.product_image_path(5),
            self.paths.root / "assets" / "dzine" / "products" / "05.png",
        )
        self.assertEqual(
            self.paths.product_image_path(1),
            self.paths.root / "assets" / "dzine" / "products" / "01.png",
        )

    def test_chunk_path(self):
        self.assertEqual(
            self.paths.chunk_path(0),
            self.paths.root / "audio" / "voice" / "chunks" / "00.mp3",
        )
        self.assertEqual(
            self.paths.chunk_path(3),
            self.paths.root / "audio" / "voice" / "chunks" / "03.mp3",
        )

    def test_ensure_dirs_creates_structure(self):
        self.paths.ensure_dirs()
        expected_dirs = [
            self.paths.root / "inputs",
            self.paths.prompts_dir,
            self.paths.assets_dzine / "products",
            self.paths.assets_amazon,
            self.paths.audio_chunks,
            self.paths.audio_music,
            self.paths.audio_sfx,
            self.paths.resolve_dir,
            self.paths.export_dir,
        ]
        for d in expected_dirs:
            self.assertTrue(d.is_dir(), f"Missing directory: {d}")

    def test_ensure_dirs_idempotent(self):
        self.paths.ensure_dirs()
        self.paths.ensure_dirs()  # should not raise
        self.assertTrue(self.paths.root.is_dir())

    def test_status_json_path(self):
        self.assertEqual(
            self.paths.status_json,
            self.paths.root / "status.json",
        )


class TestPipelineInit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.videos_base = Path(self.tmp.name)
        self.patchers = [
            patch("tools.lib.video_paths.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status._cache", {}),
            # Suppress Telegram notifications
            patch("tools.lib.notify.send_telegram", return_value=False),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    def test_init_creates_structure(self):
        from tools.pipeline import cmd_init
        args = _make_args(video_id="test-init", niche="portable speakers", force=False)
        result = cmd_init(args)
        self.assertEqual(result, 0)

        paths = VideoPaths("test-init")
        self.assertTrue(paths.root.is_dir())
        self.assertTrue(paths.products_json.is_file())
        self.assertTrue(paths.niche_txt.is_file())

        # Check niche content
        niche = paths.niche_txt.read_text().strip()
        self.assertEqual(niche, "portable speakers")

        # Check products.json template
        data = json.loads(paths.products_json.read_text())
        self.assertEqual(len(data["products"]), 5)
        self.assertEqual(data["keyword"], "portable speakers")

    def test_init_refuses_existing_without_force(self):
        from tools.pipeline import cmd_init
        args = _make_args(video_id="test-exist", niche="speakers", force=False)
        cmd_init(args)  # first call

        result = cmd_init(args)  # second call without force
        self.assertEqual(result, 1)

    def test_init_allows_force(self):
        from tools.pipeline import cmd_init
        args = _make_args(video_id="test-force", niche="speakers", force=False)
        cmd_init(args)

        args.force = True
        result = cmd_init(args)
        self.assertEqual(result, 0)


class TestPipelineResearch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.videos_base = Path(self.tmp.name)
        self.patchers = [
            patch("tools.lib.video_paths.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status._cache", {}),
            patch("tools.lib.amazon_research.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.notify.send_telegram", return_value=False),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    def test_research_missing_products(self):
        from tools.pipeline import cmd_research
        # Create minimal structure without products.json
        paths = VideoPaths("test-res")
        paths.ensure_dirs()

        args = _make_args(video_id="test-res", mode="build")
        result = cmd_research(args)
        self.assertEqual(result, 2)  # action_required

    def test_research_valid_products(self):
        from tools.pipeline import cmd_init, cmd_research
        from tools.lib.pipeline_status import start_pipeline

        paths = VideoPaths("test-res-ok")
        paths.ensure_dirs()
        start_pipeline("test-res-ok")

        # Write valid products
        data = {
            "keyword": "speakers",
            "products": [
                {"rank": r, "name": f"Product {r}", "amazon_url": f"https://amazon.com/dp/B00{r}"}
                for r in [5, 4, 3, 2, 1]
            ],
        }
        paths.products_json.write_text(json.dumps(data), encoding="utf-8")

        args = _make_args(video_id="test-res-ok", mode="build")
        result = cmd_research(args)
        self.assertEqual(result, 0)

    def test_research_invalid_products(self):
        from tools.lib.pipeline_status import start_pipeline

        paths = VideoPaths("test-res-bad")
        paths.ensure_dirs()
        start_pipeline("test-res-bad")

        # Write invalid products (missing names)
        data = {
            "keyword": "speakers",
            "products": [
                {"rank": r, "name": "", "amazon_url": ""}
                for r in [5, 4, 3, 2, 1]
            ],
        }
        paths.products_json.write_text(json.dumps(data), encoding="utf-8")

        from tools.pipeline import cmd_research
        args = _make_args(video_id="test-res-bad", mode="build")
        result = cmd_research(args)
        self.assertEqual(result, 1)


class TestPipelineScript(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.videos_base = Path(self.tmp.name)
        self.patchers = [
            patch("tools.lib.video_paths.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status._cache", {}),
            patch("tools.lib.amazon_research.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.notify.send_telegram", return_value=False),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    def test_script_generates_prompts(self):
        from tools.pipeline import cmd_script
        from tools.lib.pipeline_status import start_pipeline

        paths = VideoPaths("test-script")
        paths.ensure_dirs()
        start_pipeline("test-script")

        # Write niche
        paths.niche_txt.write_text("portable speakers\n", encoding="utf-8")

        # Write valid products
        data = {
            "keyword": "speakers",
            "products": [
                {"rank": r, "name": f"Product {r}", "amazon_url": f"https://amazon.com/dp/B00{r}"}
                for r in [5, 4, 3, 2, 1]
            ],
        }
        paths.products_json.write_text(json.dumps(data), encoding="utf-8")

        args = _make_args(video_id="test-script", charismatic="reality_check")
        result = cmd_script(args)
        # No script.txt yet, so it should return action_required
        self.assertEqual(result, 2)

        # Check prompts were generated
        self.assertTrue((paths.prompts_dir / "extraction_prompt.txt").is_file())
        self.assertTrue((paths.prompts_dir / "draft_prompt.txt").is_file())
        self.assertTrue((paths.prompts_dir / "refine_prompt.txt").is_file())

        # Check template
        template = paths.root / "script" / "script_template.txt"
        self.assertTrue(template.is_file())
        content = template.read_text()
        self.assertIn("[HOOK]", content)
        self.assertIn("[PRODUCT_5]", content)
        self.assertIn("[CONCLUSION]", content)

    def test_script_missing_products(self):
        from tools.pipeline import cmd_script

        paths = VideoPaths("test-script-nop")
        paths.ensure_dirs()
        paths.niche_txt.write_text("speakers\n", encoding="utf-8")

        args = _make_args(video_id="test-script-nop", charismatic="reality_check")
        result = cmd_script(args)
        self.assertEqual(result, 2)


class TestPipelineStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.videos_base = Path(self.tmp.name)
        self.patchers = [
            patch("tools.lib.video_paths.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status._cache", {}),
            patch("tools.lib.notify.send_telegram", return_value=False),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    def test_status_no_videos(self):
        from tools.pipeline import cmd_status
        args = _make_args(video_id="", all=True)
        result = cmd_status(args)
        self.assertEqual(result, 0)

    def test_status_single_video(self):
        from tools.pipeline import cmd_status, cmd_init
        args = _make_args(video_id="test-status", niche="speakers", force=False)
        cmd_init(args)

        args = _make_args(video_id="test-status", all=False)
        result = cmd_status(args)
        # Should return action_required since nothing is done yet
        self.assertEqual(result, 2)

    def test_status_all(self):
        from tools.pipeline import cmd_status, cmd_init
        args = _make_args(video_id="test-s1", niche="speakers", force=False)
        cmd_init(args)
        args = _make_args(video_id="test-s2", niche="headphones", force=False)
        cmd_init(args)

        # Clear cache between operations
        from tools.lib import pipeline_status
        pipeline_status._cache.clear()

        args = _make_args(video_id="", all=True)
        result = cmd_status(args)
        self.assertEqual(result, 2)  # has active videos


class TestPipelineStatusPath(unittest.TestCase):
    """Test that status path resolution works for both .status.json and status.json."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.videos_base = Path(self.tmp.name)
        self.patchers = [
            patch("tools.lib.pipeline_status.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status._cache", {}),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    def test_prefers_new_status_json(self):
        from tools.lib.pipeline_status import _status_path
        vid = "test-new"
        vdir = self.videos_base / vid
        vdir.mkdir(parents=True)
        # Create both files
        (vdir / ".status.json").write_text("{}")
        (vdir / "status.json").write_text("{}")
        path = _status_path(vid)
        self.assertEqual(path.name, "status.json")

    def test_falls_back_to_legacy(self):
        from tools.lib.pipeline_status import _status_path
        vid = "test-legacy"
        vdir = self.videos_base / vid
        vdir.mkdir(parents=True)
        (vdir / ".status.json").write_text("{}")
        path = _status_path(vid)
        self.assertEqual(path.name, ".status.json")

    def test_defaults_to_new_for_fresh(self):
        from tools.lib.pipeline_status import _status_path
        vid = "test-fresh"
        vdir = self.videos_base / vid
        vdir.mkdir(parents=True)
        path = _status_path(vid)
        self.assertEqual(path.name, "status.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(**kwargs):
    """Create an argparse-like namespace."""
    import argparse
    return argparse.Namespace(**kwargs)


if __name__ == "__main__":
    unittest.main()
