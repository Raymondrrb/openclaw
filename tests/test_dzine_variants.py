"""Unit tests for Dzine multi-variant image generation system."""

import tempfile
import unittest
from pathlib import Path

from tools.lib.dzine_schema import (
    IMAGE_VARIANTS,
    VARIANT_RESOLUTIONS,
    VARIANT_TEMPLATES,
    VARIANT_NEGATIVES,
    DZINE_IMAGES_PER_PRODUCT,
    DZINE_EXTRA_FOR_TOP2,
    DzineRequest,
    build_prompts,
    detect_category,
    validate_request,
    variants_for_rank,
)
from tools.lib.video_paths import VideoPaths


class TestImageVariants(unittest.TestCase):

    def test_image_variants_constant(self):
        self.assertEqual(len(IMAGE_VARIANTS), 5)
        self.assertIn("hero", IMAGE_VARIANTS)
        self.assertIn("usage1", IMAGE_VARIANTS)
        self.assertIn("usage2", IMAGE_VARIANTS)
        self.assertIn("detail", IMAGE_VARIANTS)
        self.assertIn("mood", IMAGE_VARIANTS)

    def test_variant_resolutions_defined(self):
        for v in IMAGE_VARIANTS:
            self.assertIn(v, VARIANT_RESOLUTIONS)
            w, h = VARIANT_RESOLUTIONS[v]
            self.assertGreaterEqual(w, 1024)
            self.assertGreaterEqual(h, 1024)


class TestVariantsForRank(unittest.TestCase):

    def test_base_rank_gets_3_variants(self):
        """Ranks 3-5 get base variants: hero, usage1, detail."""
        for rank in [3, 4, 5]:
            variants = variants_for_rank(rank)
            self.assertEqual(len(variants), 3, f"rank {rank}")
            self.assertEqual(variants, ("hero", "usage1", "detail"))

    def test_rank_2_gets_mood(self):
        """Rank 2 gets base + mood = 4 variants."""
        variants = variants_for_rank(2)
        self.assertEqual(len(variants), 4)
        self.assertIn("mood", variants)

    def test_rank_1_gets_usage2_and_mood(self):
        """Rank 1 gets base + usage2 + mood = 5 variants."""
        variants = variants_for_rank(1)
        self.assertEqual(len(variants), 5)
        self.assertIn("usage2", variants)
        self.assertIn("mood", variants)

    def test_total_images(self):
        """1 thumbnail + sum of per-rank variants."""
        total = 1  # thumbnail
        for rank in [5, 4, 3, 2, 1]:
            total += len(variants_for_rank(rank))
        # 1 + 3+3+3+4+5 = 19 with hierarchy
        self.assertEqual(total, 19)


class TestDetectCategory(unittest.TestCase):

    def test_exact_match(self):
        self.assertEqual(detect_category("wireless earbuds"), "audio")

    def test_exact_match_kitchen(self):
        self.assertEqual(detect_category("air fryers"), "kitchen")

    def test_keyword_fallback(self):
        self.assertEqual(detect_category("gaming mouse pad xl"), "gaming")

    def test_unknown_niche_returns_default(self):
        self.assertEqual(detect_category("quantum computers"), "default")

    def test_empty_niche_returns_default(self):
        self.assertEqual(detect_category(""), "default")

    def test_case_insensitive(self):
        self.assertEqual(detect_category("Wireless Earbuds"), "audio")


class TestBuildPromptsVariants(unittest.TestCase):

    def test_hero_prompt_contains_cinematic(self):
        req = DzineRequest(
            asset_type="product", product_name="Test Headphones",
            image_variant="hero", niche_category="audio",
        )
        built = build_prompts(req)
        self.assertIn("cinematic", built.prompt.lower())

    def test_usage1_kitchen_scene(self):
        req = DzineRequest(
            asset_type="product", product_name="Test Blender",
            image_variant="usage1", niche_category="kitchen",
        )
        built = build_prompts(req)
        prompt_lower = built.prompt.lower()
        self.assertTrue("counter" in prompt_lower or "kitchen" in prompt_lower)

    def test_usage1_default_fallback(self):
        req = DzineRequest(
            asset_type="product", product_name="Test Widget",
            image_variant="usage1", niche_category="unknown_category",
        )
        built = build_prompts(req)
        # Should use default template (not crash)
        self.assertIn("Test Widget", built.prompt)
        self.assertGreater(len(built.prompt), 50)

    def test_detail_prompt_contains_macro(self):
        req = DzineRequest(
            asset_type="product", product_name="Test Mouse",
            image_variant="detail",
        )
        built = build_prompts(req)
        self.assertIn("macro", built.prompt.lower())

    def test_mood_prompt_contains_atmospheric(self):
        req = DzineRequest(
            asset_type="product", product_name="Test Speaker",
            image_variant="mood",
        )
        built = build_prompts(req)
        self.assertIn("atmospheric", built.prompt.lower())

    def test_variant_with_reference_image(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake png data")
            tmp = f.name
        try:
            req = DzineRequest(
                asset_type="product", product_name="Test Earbuds",
                image_variant="hero", reference_image=tmp,
            )
            built = build_prompts(req)
            self.assertIn("reference image", built.prompt.lower())
        finally:
            Path(tmp).unlink()

    def test_variant_resolution_applied(self):
        req = DzineRequest(
            asset_type="product", product_name="X",
            image_variant="hero",
        )
        built = build_prompts(req)
        self.assertEqual(built.width, 2048)
        self.assertEqual(built.height, 1152)

    def test_detail_resolution_square(self):
        req = DzineRequest(
            asset_type="product", product_name="X",
            image_variant="detail",
        )
        built = build_prompts(req)
        self.assertEqual(built.width, 2048)
        self.assertEqual(built.height, 2048)

    def test_no_variant_backward_compat(self):
        """Empty image_variant uses existing product template."""
        req = DzineRequest(
            asset_type="product", product_name="Test Product",
        )
        built = build_prompts(req)
        self.assertIn("Studio-quality", built.prompt)
        self.assertEqual(built.width, 2048)
        self.assertEqual(built.height, 2048)

    def test_variant_negative_prompt(self):
        req = DzineRequest(
            asset_type="product", product_name="X",
            image_variant="usage1",
        )
        built = build_prompts(req)
        self.assertIn("visible faces", built.negative_prompt)


class TestValidateVariant(unittest.TestCase):

    def test_valid_variant_accepted(self):
        req = DzineRequest(
            asset_type="product", product_name="X",
            image_variant="hero",
        )
        self.assertEqual(validate_request(req), [])

    def test_invalid_variant_rejected(self):
        req = DzineRequest(
            asset_type="product", product_name="X",
            image_variant="closeup",
        )
        errors = validate_request(req)
        self.assertTrue(any("image_variant" in e for e in errors))

    def test_empty_variant_accepted(self):
        req = DzineRequest(
            asset_type="product", product_name="X",
            image_variant="",
        )
        self.assertEqual(validate_request(req), [])


class TestVideoPathsVariants(unittest.TestCase):

    def setUp(self):
        self.paths = VideoPaths("test-vid-001")

    def test_product_image_path_with_variant(self):
        p = self.paths.product_image_path(5, "hero")
        self.assertTrue(str(p).endswith("05_hero.png"))

    def test_product_image_path_without_variant(self):
        p = self.paths.product_image_path(5)
        self.assertTrue(str(p).endswith("05.png"))

    def test_product_prompt_path(self):
        p = self.paths.product_prompt_path(5, "hero")
        self.assertTrue(str(p).endswith("prompts/05_hero.txt"))

    def test_thumbnail_prompt_path(self):
        p = self.paths.thumbnail_prompt_path()
        self.assertTrue(str(p).endswith("prompts/thumbnail.txt"))

    def test_amazon_ref_image(self):
        p = self.paths.amazon_ref_image(5)
        self.assertTrue(str(p).endswith("amazon/05_ref.jpg"))

    def test_ensure_dirs_creates_prompts(self):
        with tempfile.TemporaryDirectory() as tmp:
            import tools.lib.video_paths as vp
            orig = vp.VIDEOS_BASE
            try:
                vp.VIDEOS_BASE = Path(tmp)
                paths = VideoPaths("test-dirs")
                paths.root = Path(tmp) / "test-dirs"
                paths.assets_dzine = paths.root / "assets" / "dzine"
                paths.assets_amazon = paths.root / "assets" / "amazon"
                paths.audio_chunks = paths.root / "audio" / "voice" / "chunks"
                paths.audio_music = paths.root / "audio" / "music"
                paths.audio_sfx = paths.root / "audio" / "sfx"
                paths.resolve_dir = paths.root / "resolve"
                paths.export_dir = paths.root / "export"
                paths.prompts_dir = paths.root / "script" / "prompts"
                paths.ensure_dirs()
                self.assertTrue((paths.assets_dzine / "prompts").is_dir())
            finally:
                vp.VIDEOS_BASE = orig


class TestDiscoverAssetsVariants(unittest.TestCase):

    def test_discovers_variant_images(self):
        from tools.lib.resolve_schema import discover_assets
        with tempfile.TemporaryDirectory() as tmp:
            vd = Path(tmp)
            products_dir = vd / "assets" / "dzine" / "products"
            products_dir.mkdir(parents=True)
            # Create variant images
            (products_dir / "05_hero.png").write_bytes(b"x" * 100)
            (products_dir / "05_usage1.png").write_bytes(b"x" * 100)
            (products_dir / "05_detail.png").write_bytes(b"x" * 100)

            assets = discover_assets(vd)
            dzine_files = assets["products"][5]["dzine"]
            self.assertEqual(len(dzine_files), 3)
            self.assertIn("assets/dzine/products/05_hero.png", dzine_files)
            self.assertIn("assets/dzine/products/05_usage1.png", dzine_files)
            self.assertIn("assets/dzine/products/05_detail.png", dzine_files)

    def test_discovers_legacy_single_image(self):
        from tools.lib.resolve_schema import discover_assets
        with tempfile.TemporaryDirectory() as tmp:
            vd = Path(tmp)
            products_dir = vd / "assets" / "dzine" / "products"
            products_dir.mkdir(parents=True)
            (products_dir / "05.png").write_bytes(b"x" * 100)

            assets = discover_assets(vd)
            dzine_files = assets["products"][5]["dzine"]
            self.assertEqual(len(dzine_files), 1)
            self.assertIn("assets/dzine/products/05.png", dzine_files)

    def test_no_cross_rank_contamination(self):
        """05_hero.png should not appear in rank 4's assets."""
        from tools.lib.resolve_schema import discover_assets
        with tempfile.TemporaryDirectory() as tmp:
            vd = Path(tmp)
            products_dir = vd / "assets" / "dzine" / "products"
            products_dir.mkdir(parents=True)
            (products_dir / "05_hero.png").write_bytes(b"x" * 100)
            (products_dir / "04_hero.png").write_bytes(b"x" * 100)

            assets = discover_assets(vd)
            self.assertEqual(len(assets["products"][5]["dzine"]), 1)
            self.assertEqual(len(assets["products"][4]["dzine"]), 1)
            self.assertIn("05_hero", assets["products"][5]["dzine"][0])
            self.assertIn("04_hero", assets["products"][4]["dzine"][0])


class TestImageQAResult(unittest.TestCase):
    """Test ImageQAResult dataclass and _guess_media_type."""

    def test_image_qa_result_defaults(self):
        from tools.lib.dzine_browser import ImageQAResult
        qa = ImageQAResult()
        self.assertEqual(qa.total, 0.0)
        self.assertFalse(qa.video_ready)
        self.assertEqual(qa.issues, [])
        self.assertEqual(qa.error, "")

    def test_image_qa_result_with_values(self):
        from tools.lib.dzine_browser import ImageQAResult
        qa = ImageQAResult(
            product_intact=9.0,
            color_fidelity=8.5,
            no_phone_fragments=10.0,
            no_ghosting=9.0,
            background_quality=8.0,
            overall_composition=8.5,
            total=8.8,
            video_ready=True,
        )
        self.assertTrue(qa.video_ready)
        self.assertAlmostEqual(qa.total, 8.8)

    def test_image_qa_result_with_issues(self):
        from tools.lib.dzine_browser import ImageQAResult
        qa = ImageQAResult(
            total=5.0,
            issues=["phone fragment on right edge", "ghosting on bottom"],
            video_ready=False,
        )
        self.assertEqual(len(qa.issues), 2)
        self.assertFalse(qa.video_ready)

    def test_guess_media_type_png(self):
        from tools.lib.dzine_browser import _guess_media_type
        png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        self.assertEqual(_guess_media_type(png_header), "image/png")

    def test_guess_media_type_jpeg(self):
        from tools.lib.dzine_browser import _guess_media_type
        jpeg_header = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        self.assertEqual(_guess_media_type(jpeg_header), "image/jpeg")

    def test_guess_media_type_webp(self):
        from tools.lib.dzine_browser import _guess_media_type
        webp_header = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 100
        self.assertEqual(_guess_media_type(webp_header), "image/webp")

    def test_guess_media_type_unknown(self):
        from tools.lib.dzine_browser import _guess_media_type
        self.assertEqual(_guess_media_type(b"\x00" * 100), "image/png")

    def test_analyze_no_api_key(self):
        """Without API key, _analyze_image_qa returns error gracefully."""
        import os
        from tools.lib.dzine_browser import _analyze_image_qa
        old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            result = _analyze_image_qa(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            self.assertIn("ANTHROPIC_API_KEY", result.error)
        finally:
            if old_key:
                os.environ["ANTHROPIC_API_KEY"] = old_key

    def test_analyze_generated_image_missing_file(self):
        """analyze_generated_image returns error for missing files."""
        from tools.lib.dzine_browser import analyze_generated_image
        result = analyze_generated_image(Path("/nonexistent/image.png"))
        self.assertIn("not found", result.error)


if __name__ == "__main__":
    unittest.main()
