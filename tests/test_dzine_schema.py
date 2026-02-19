"""Unit tests for tools.lib.dzine_schema — Amazon Associates visual system."""

import tempfile
import unittest
from pathlib import Path

from tools.lib.dzine_schema import (
    ASSET_TYPES,
    DEFAULT_RESOLUTIONS,
    IMAGE_VARIANTS,
    MAX_PROMPT_LENGTH,
    MODEL_ROUTING,
    NEGATIVE_PROMPTS,
    PROMPT_TEMPLATES,
    STYLES,
    VARIANT_MODEL_ROUTING,
    VARIANT_TEMPLATES,
    DzineRequest,
    build_prompts,
    recommended_model,
    validate_request,
)


class TestValidateRequest(unittest.TestCase):

    def test_valid_thumbnail(self):
        req = DzineRequest(
            asset_type="thumbnail",
            product_name="Test Product A",
            key_message="Top Pick 2026",
        )
        self.assertEqual(validate_request(req), [])

    def test_valid_product(self):
        req = DzineRequest(asset_type="product", product_name="Test Product B")
        self.assertEqual(validate_request(req), [])

    def test_valid_background(self):
        req = DzineRequest(asset_type="background")
        self.assertEqual(validate_request(req), [])

    def test_valid_avatar_base(self):
        req = DzineRequest(asset_type="avatar_base")
        self.assertEqual(validate_request(req), [])

    def test_invalid_asset_type(self):
        req = DzineRequest(asset_type="banner")
        errors = validate_request(req)
        self.assertEqual(len(errors), 1)
        self.assertIn("Invalid asset_type", errors[0])

    def test_missing_required_fields_thumbnail(self):
        req = DzineRequest(asset_type="thumbnail")
        errors = validate_request(req)
        self.assertTrue(any("product_name" in e for e in errors))
        self.assertTrue(any("key_message" in e for e in errors))

    def test_missing_product_name_for_product(self):
        req = DzineRequest(asset_type="product")
        errors = validate_request(req)
        self.assertEqual(len(errors), 1)
        self.assertIn("product_name", errors[0])

    def test_invalid_style(self):
        req = DzineRequest(asset_type="avatar_base", style="anime")
        errors = validate_request(req)
        self.assertEqual(len(errors), 1)
        self.assertIn("Invalid style", errors[0])

    def test_valid_styles(self):
        for style in STYLES:
            req = DzineRequest(asset_type="avatar_base", style=style)
            self.assertEqual(validate_request(req), [], f"Style {style!r} should be valid")

    def test_thumbnail_key_message_max_4_words(self):
        req = DzineRequest(
            asset_type="thumbnail",
            product_name="X",
            key_message="This Is Way Too Many Words",
        )
        errors = validate_request(req)
        self.assertTrue(any("4 words max" in e for e in errors))

    def test_thumbnail_key_message_4_words_ok(self):
        req = DzineRequest(
            asset_type="thumbnail",
            product_name="X",
            key_message="Top Pick Ever Made",
        )
        self.assertEqual(validate_request(req), [])

    def test_prompt_override_length_limit(self):
        req = DzineRequest(
            asset_type="avatar_base",
            prompt_override="x" * (MAX_PROMPT_LENGTH + 1),
        )
        errors = validate_request(req)
        self.assertTrue(any("prompt_override" in e for e in errors))

    def test_reference_image_not_found(self):
        req = DzineRequest(
            asset_type="product",
            product_name="X",
            reference_image="/nonexistent/image.png",
        )
        errors = validate_request(req)
        self.assertTrue(any("Reference image not found" in e for e in errors))

    def test_reference_image_valid(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake png")
            tmp = f.name
        try:
            req = DzineRequest(
                asset_type="product",
                product_name="X",
                reference_image=tmp,
            )
            self.assertEqual(validate_request(req), [])
        finally:
            Path(tmp).unlink()

    def test_width_too_small(self):
        req = DzineRequest(asset_type="avatar_base", width=100)
        errors = validate_request(req)
        self.assertTrue(any("width" in e for e in errors))

    def test_width_too_large(self):
        req = DzineRequest(asset_type="avatar_base", width=5000)
        errors = validate_request(req)
        self.assertTrue(any("width" in e for e in errors))

    def test_height_bounds(self):
        req = DzineRequest(asset_type="avatar_base", height=100)
        errors = validate_request(req)
        self.assertTrue(any("height" in e for e in errors))

    def test_zero_dimensions_are_ok(self):
        """Zero means 'use default' — should not trigger errors."""
        req = DzineRequest(asset_type="avatar_base", width=0, height=0)
        self.assertEqual(validate_request(req), [])

    def test_all_asset_types_have_defaults(self):
        for at in ASSET_TYPES:
            self.assertIn(at, DEFAULT_RESOLUTIONS)

    def test_all_asset_types_have_negatives(self):
        for at in ASSET_TYPES:
            self.assertIn(at, NEGATIVE_PROMPTS)

    def test_all_asset_types_have_templates(self):
        for at in ASSET_TYPES:
            self.assertIn(at, PROMPT_TEMPLATES)


class TestBuildPrompts(unittest.TestCase):

    def test_thumbnail_contains_product_name(self):
        req = DzineRequest(
            asset_type="thumbnail",
            product_name="Test Product A",
            key_message="Top Pick",
        )
        built = build_prompts(req)
        self.assertIn("Test Product A", built.prompt)

    def test_thumbnail_resolution(self):
        req = DzineRequest(
            asset_type="thumbnail",
            product_name="X",
            key_message="Y",
        )
        built = build_prompts(req)
        self.assertEqual(built.width, 2048)
        self.assertEqual(built.height, 1152)

    def test_product_resolution(self):
        req = DzineRequest(asset_type="product", product_name="X")
        built = build_prompts(req)
        self.assertEqual(built.width, 2048)
        self.assertEqual(built.height, 2048)

    def test_background_resolution(self):
        req = DzineRequest(asset_type="background")
        built = build_prompts(req)
        self.assertEqual(built.width, 2048)
        self.assertEqual(built.height, 1152)

    def test_avatar_resolution(self):
        req = DzineRequest(asset_type="avatar_base")
        built = build_prompts(req)
        self.assertEqual(built.width, 2048)
        self.assertEqual(built.height, 2048)

    def test_custom_resolution_preserved(self):
        req = DzineRequest(
            asset_type="thumbnail",
            product_name="X",
            key_message="Y",
            width=1920,
            height=1080,
        )
        built = build_prompts(req)
        self.assertEqual(built.width, 1920)
        self.assertEqual(built.height, 1080)

    def test_prompt_override_bypasses_templates(self):
        req = DzineRequest(
            asset_type="thumbnail",
            product_name="X",
            key_message="Y",
            prompt_override="Custom prompt for everything",
        )
        built = build_prompts(req)
        self.assertEqual(built.prompt, "Custom prompt for everything")
        self.assertIsNone(built.prompt_override)  # consumed

    def test_negative_prompt_default(self):
        req = DzineRequest(asset_type="product", product_name="Test Product B")
        built = build_prompts(req)
        self.assertEqual(built.negative_prompt, NEGATIVE_PROMPTS["product"])

    def test_custom_negative_preserved(self):
        req = DzineRequest(
            asset_type="product",
            product_name="X",
            negative_prompt="no cats",
        )
        built = build_prompts(req)
        self.assertEqual(built.negative_prompt, "no cats")

    def test_product_with_reference_uses_ref_template(self):
        """When reference_image is set, product uses the _with_ref template."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake png")
            tmp = f.name
        try:
            req = DzineRequest(
                asset_type="product",
                product_name="Test Product B",
                reference_image=tmp,
            )
            built = build_prompts(req)
            self.assertIn("reference image", built.prompt.lower())
            self.assertIn("Test Product B", built.prompt)
        finally:
            Path(tmp).unlink()

    def test_product_without_reference_no_ref_text(self):
        req = DzineRequest(asset_type="product", product_name="Test Product B")
        built = build_prompts(req)
        self.assertNotIn("reference image", built.prompt.lower())

    def test_background_no_product_needed(self):
        req = DzineRequest(asset_type="background")
        built = build_prompts(req)
        self.assertIn("cinematic background", built.prompt.lower())
        self.assertTrue(len(built.prompt) > 0)

    def test_avatar_base_prompt(self):
        req = DzineRequest(asset_type="avatar_base")
        built = build_prompts(req)
        self.assertIn("confident modern host", built.prompt.lower())
        self.assertIn("rim light", built.prompt.lower())

    def test_reference_image_preserved(self):
        req = DzineRequest(
            asset_type="product",
            product_name="X",
            reference_image="/some/path.png",
        )
        built = build_prompts(req)
        self.assertEqual(built.reference_image, "/some/path.png")

    def test_custom_prompt_preserved(self):
        req = DzineRequest(
            asset_type="avatar_base",
            prompt="My custom prompt text here",
        )
        built = build_prompts(req)
        self.assertEqual(built.prompt, "My custom prompt text here")

    def test_thumbnail_template_updated(self):
        """Thumbnail template should not contain 'Add bold headline text'."""
        self.assertNotIn("Add bold headline text", PROMPT_TEMPLATES["thumbnail"])

    def test_all_variants_have_templates(self):
        """Every IMAGE_VARIANT must have a 'default' key in VARIANT_TEMPLATES."""
        for variant in IMAGE_VARIANTS:
            self.assertIn(variant, VARIANT_TEMPLATES, f"Missing template for {variant}")
            self.assertIn("default", VARIANT_TEMPLATES[variant],
                         f"Missing 'default' key in VARIANT_TEMPLATES[{variant!r}]")


class TestModelRouting(unittest.TestCase):
    """Test model selection logic."""

    def test_thumbnail_default_is_nano_banana(self):
        self.assertEqual(recommended_model("thumbnail"), "Nano Banana Pro")

    def test_product_default_is_realistic(self):
        self.assertEqual(recommended_model("product"), "Realistic Product")

    def test_background_is_nano_banana(self):
        self.assertEqual(recommended_model("background"), "Nano Banana Pro")

    def test_detail_variant_is_realistic(self):
        self.assertEqual(recommended_model("product", variant="detail"), "Realistic Product")

    def test_hero_variant_is_realistic(self):
        self.assertEqual(recommended_model("product", variant="hero"), "Realistic Product")

    def test_testing_mode_returns_turbo(self):
        self.assertEqual(recommended_model("thumbnail", testing=True), "Z-Image Turbo")

    def test_all_asset_types_have_routing(self):
        for at in ASSET_TYPES:
            self.assertIn(at, MODEL_ROUTING, f"Missing model routing for {at}")

    def test_all_variants_have_routing(self):
        for v in IMAGE_VARIANTS:
            self.assertIn(v, VARIANT_MODEL_ROUTING, f"Missing variant model routing for {v}")

    def test_product_faithful_has_no_model(self):
        """product_faithful uses BG Remove + Expand, not a generation model."""
        self.assertIsNone(MODEL_ROUTING["product_faithful"]["primary"])


if __name__ == "__main__":
    unittest.main()
