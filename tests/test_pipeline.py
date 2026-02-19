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
            patch("tools.pipeline._log_error"),
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

        args = _make_args(video_id="test-res", mode="build", no_approval=True)
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
                {
                    "rank": r,
                    "name": f"Product {r}",
                    "amazon_url": f"https://amazon.com/dp/B00{r}",
                    "downside": "Minor drawback noted",
                    "benefits": ["Good sound", "Portable"],
                }
                for r in [5, 4, 3, 2, 1]
            ],
        }
        paths.products_json.write_text(json.dumps(data), encoding="utf-8")

        args = _make_args(video_id="test-res-ok", mode="build", no_approval=True)
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
        args = _make_args(video_id="test-res-bad", mode="build", no_approval=True)
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
            patch("tools.pipeline._log_error"),
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
                {
                    "rank": r,
                    "name": f"Product {r}",
                    "amazon_url": f"https://amazon.com/dp/B00{r}",
                    "downside": "Minor drawback noted",
                    "benefits": ["Good sound", "Portable"],
                }
                for r in [5, 4, 3, 2, 1]
            ],
        }
        paths.products_json.write_text(json.dumps(data), encoding="utf-8")

        args = _make_args(video_id="test-script", charismatic="reality_check", generate=False, no_approval=True)
        result = cmd_script(args)
        # No script.txt yet and generate=False, so it should return action_required
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

        args = _make_args(video_id="test-script-nop", charismatic="reality_check", no_approval=True)
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


class TestPipelineDayCluster(unittest.TestCase):
    """Tests for cmd_day cluster integration."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.videos_base = Path(self.tmp.name)
        self.data_dir = Path(self.tmp.name) / "data"
        self.data_dir.mkdir()
        self.patchers = [
            patch("tools.lib.video_paths.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status._cache", {}),
            patch("tools.lib.notify.send_telegram", return_value=False),
            patch("tools.pipeline._log_error"),
            patch("tools.cluster_manager.DATA_DIR", self.data_dir),
            patch("tools.cluster_manager.CLUSTERS_PATH", self.data_dir / "clusters.json"),
            patch("tools.cluster_manager.CLUSTER_HISTORY_PATH", self.data_dir / "cluster_history.json"),
        ]
        for p in self.patchers:
            p.start()

        # Write minimal clusters.json
        clusters = [
            {
                "name": "Test Cluster",
                "slug": "test_cluster",
                "micro_niches": [
                    {
                        "subcategory": f"test niche {i}",
                        "buyer_pain": f"test pain {i}",
                        "intent_phrase": f"best test niche {i}",
                        "price_min": 120,
                        "price_max": 300,
                        "must_have_features": ["feature_a"],
                        "forbidden_variants": ["bad_variant"],
                    }
                    for i in range(5)
                ],
            },
        ]
        (self.data_dir / "clusters.json").write_text(json.dumps(clusters), encoding="utf-8")
        (self.data_dir / "cluster_history.json").write_text("[]", encoding="utf-8")

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    def test_day_writes_cluster_txt(self):
        """cmd_day creates cluster.txt when using cluster selection."""
        from tools.pipeline import cmd_day

        # Mock research + script-brief to avoid actual work
        with patch("tools.pipeline.cmd_research", return_value=0), \
             patch("tools.pipeline.cmd_script_brief", return_value=0):
            args = _make_args(video_id="test-cluster", niche="", cluster="", force=False, no_approval=True)
            cmd_day(args)

        paths = VideoPaths("test-cluster")
        self.assertTrue(paths.cluster_txt.is_file(), "cluster.txt should be written")
        content = paths.cluster_txt.read_text(encoding="utf-8").strip()
        self.assertEqual(content, "test_cluster")

    def test_day_writes_micro_niche_json(self):
        """cmd_day creates micro_niche.json with correct schema."""
        from tools.pipeline import cmd_day

        with patch("tools.pipeline.cmd_research", return_value=0), \
             patch("tools.pipeline.cmd_script_brief", return_value=0):
            args = _make_args(video_id="test-mn", niche="", cluster="", force=False, no_approval=True)
            cmd_day(args)

        paths = VideoPaths("test-mn")
        self.assertTrue(paths.micro_niche_json.is_file(), "micro_niche.json should be written")
        data = json.loads(paths.micro_niche_json.read_text(encoding="utf-8"))
        self.assertIn("subcategory", data)
        self.assertIn("buyer_pain", data)
        self.assertIn("intent_phrase", data)
        self.assertIn("price_min", data)
        self.assertIn("price_max", data)
        self.assertIn("cluster_slug", data)

    def test_day_niche_override_skips_cluster(self):
        """--niche flag bypasses cluster system."""
        from tools.pipeline import cmd_day

        with patch("tools.pipeline.cmd_research", return_value=0), \
             patch("tools.pipeline.cmd_script_brief", return_value=0):
            args = _make_args(
                video_id="test-override", niche="wireless earbuds",
                cluster="", force=False, no_approval=True,
            )
            cmd_day(args)

        paths = VideoPaths("test-override")
        # cluster.txt should NOT be written when niche override is used
        self.assertFalse(paths.cluster_txt.is_file())


class TestTop5BuyerLabels(unittest.TestCase):
    """Tests for buyer-centric labels in top5_ranker."""

    def _make_products(self, n=7):
        """Make verified product dicts for testing."""
        return [
            {
                "product_name": f"Product {i}",
                "brand": f"Brand{i}",
                "asin": f"B00{i}",
                "amazon_price": f"${150 + i * 30}",
                "amazon_rating": "4.5",
                "amazon_reviews": "1000",
                "evidence": [{"source": "Wirecutter", "reasons": [f"Good quality {i}"]}],
                "key_claims": [f"Rated best for feature {i}"],
                "match_confidence": "high",
            }
            for i in range(n)
        ]

    def test_new_category_labels(self):
        """Verify labels are the 5 new buyer-centric names."""
        from tools.top5_ranker import CATEGORY_SLOTS
        expected = [
            "No-Regret Pick", "Best Value", "Best Upgrade",
            "Best for Specific Scenario", "Best Alternative",
        ]
        self.assertEqual(CATEGORY_SLOTS, expected)

    def test_no_regret_pick_is_rank_1(self):
        """Highest-scored product gets 'No-Regret Pick'."""
        from tools.top5_ranker import select_top5
        products = self._make_products(7)
        top5 = select_top5(products)
        rank1 = [p for p in top5 if p["rank"] == 1][0]
        self.assertEqual(rank1["category_label"], "No-Regret Pick")

    def test_buy_avoid_present(self):
        """Every product in output has buy_this_if and avoid_this_if."""
        from tools.top5_ranker import select_top5, write_products_json
        products = self._make_products(7)
        top5 = select_top5(products)

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "products.json"
            write_products_json(top5, "test niche", out, video_id="test")
            data = json.loads(out.read_text())
            for p in data["products"]:
                self.assertIn("buy_this_if", p, f"Product rank {p['rank']} missing buy_this_if")
                self.assertIn("avoid_this_if", p, f"Product rank {p['rank']} missing avoid_this_if")
                self.assertTrue(len(p["buy_this_if"]) > 0, f"Product rank {p['rank']} buy_this_if is empty")

    def test_brand_diversity_warning(self):
        """3+ same brand triggers warning (captured via stderr)."""
        from tools.top5_ranker import _check_brand_diversity
        top5 = [
            {"brand": "Sony"}, {"brand": "Sony"}, {"brand": "Sony"},
            {"brand": "Bose"}, {"brand": "JBL"},
        ]
        warning = _check_brand_diversity(top5)
        self.assertIsNotNone(warning)
        self.assertIn("sony", warning.lower())

    def test_brand_diversity_no_warning(self):
        """All different brands: no warning."""
        from tools.top5_ranker import _check_brand_diversity
        top5 = [
            {"brand": "Sony"}, {"brand": "Bose"}, {"brand": "JBL"},
            {"brand": "Sennheiser"}, {"brand": "Audio-Technica"},
        ]
        warning = _check_brand_diversity(top5)
        self.assertIsNone(warning)


class TestContractFromMicroNiche(unittest.TestCase):
    """Test generate_contract_from_micro_niche."""

    def test_contract_from_micro_niche(self):
        from tools.cluster_manager import MicroNicheDef
        from tools.lib.subcategory_contract import generate_contract_from_micro_niche

        micro = MicroNicheDef(
            subcategory="ergonomic office chairs",
            buyer_pain="back pain",
            intent_phrase="best ergonomic chairs for back pain",
            price_min=200,
            price_max=500,
            must_have_features=["lumbar support", "adjustable armrests"],
            forbidden_variants=["gaming chair", "stool"],
        )
        contract = generate_contract_from_micro_niche(micro)
        self.assertEqual(contract.niche_name, "ergonomic office chairs")
        # forbidden_variants should be in disallowed
        disallowed_lower = [k.lower() for k in contract.disallowed_keywords]
        self.assertIn("gaming chair", disallowed_lower)
        self.assertIn("stool", disallowed_lower)

    def test_contract_augments_template(self):
        """If a template matches, micro-niche data augments it."""
        from tools.cluster_manager import MicroNicheDef
        from tools.lib.subcategory_contract import generate_contract_from_micro_niche

        micro = MicroNicheDef(
            subcategory="air fryers",
            buyer_pain="slow cooking",
            intent_phrase="best air fryers",
            must_have_features=["dishwasher-safe", "digital controls"],
            forbidden_variants=["deep fryer", "toaster oven"],
        )
        contract = generate_contract_from_micro_niche(micro)
        # Should find the air fryers template
        self.assertIn("fryer", [k.lower() for k in contract.mandatory_keywords])
        # And augment with our forbidden variant
        disallowed_lower = [k.lower() for k in contract.disallowed_keywords]
        self.assertIn("deep fryer", disallowed_lower)


if __name__ == "__main__":
    unittest.main()
