"""Unit tests for tools.lib.script_schema — video script validation system."""

import unittest

from tools.lib.script_schema import (
    AI_CLICHES,
    AVATAR_INTRO_MAX_CHARS,
    COMPLIANCE_VIOLATIONS,
    HOOK_WORD_MAX,
    HOOK_WORD_MIN,
    HYPE_WORDS,
    PRODUCT_WORD_MAX,
    PRODUCT_WORD_MIN,
    RETENTION_RESET_WORD_MAX,
    RETENTION_RESET_WORD_MIN,
    SCRIPT_WORD_MAX,
    SCRIPT_WORD_MIN,
    SECTION_ORDER,
    THUMBNAIL_HEADLINE_MAX_WORDS,
    ProductEntry,
    ScriptOutput,
    ScriptRequest,
    ScriptSection,
    build_draft_prompt,
    build_extraction_prompt,
    build_refinement_prompt,
    validate_request,
    validate_script,
)


def _make_products(count=5) -> list[ProductEntry]:
    """Helper: create valid product entries."""
    return [
        ProductEntry(
            rank=i,
            name=f"Product {i}",
            amazon_url=f"https://amazon.com/dp/B0FAKE{i:04d}",
            downside="Minor drawback noted",
            benefits=["Benefit one", "Benefit two"],
        )
        for i in range(1, count + 1)
    ]


def _filler(word_count: int) -> str:
    """Generate filler text of approximately the given word count."""
    return " ".join(["word"] * word_count)


def _make_product_section(rank: int, word_count: int = 250) -> ScriptSection:
    """Product section with a downside marker."""
    text = _filler(word_count - 5) + " however this is a minor issue"
    return ScriptSection(section_type=f"product_{rank}", content=text)


def _make_valid_output() -> ScriptOutput:
    """Build a ScriptOutput that passes all checks."""
    hook = ScriptSection(section_type="hook", content=_filler(120))
    avatar = ScriptSection(section_type="avatar_intro", content="Short intro clip text here")
    p5 = _make_product_section(5)
    p4 = _make_product_section(4)
    p3 = _make_product_section(3)
    reset = ScriptSection(section_type="retention_reset", content=_filler(65))
    p2 = _make_product_section(2)
    p1 = _make_product_section(1)
    conclusion = ScriptSection(
        section_type="conclusion",
        content=(
            "Thanks for watching. Links in the description may be affiliate links, "
            "which means I may earn a small commission at no extra cost to you. "
            + _filler(30)
        ),
    )
    return ScriptOutput(
        sections=[hook, avatar, p5, p4, p3, reset, p2, p1, conclusion],
        avatar_intro="Today I picked 5 Amazon finds worth your money. Let's begin.",
        youtube_description="Top 5 picks. Links may be affiliate links.",
        thumbnail_headlines=["Best ANC 2026", "Top Picks", "Worth It"],
    )


# ===================================================================
# Request validation
# ===================================================================


class TestValidateRequest(unittest.TestCase):

    def test_valid_request(self):
        req = ScriptRequest(niche="test niche", products=_make_products())
        self.assertEqual(validate_request(req), [])

    def test_empty_niche(self):
        req = ScriptRequest(niche="", products=_make_products())
        errors = validate_request(req)
        self.assertTrue(any("niche" in e for e in errors))

    def test_wrong_product_count(self):
        req = ScriptRequest(niche="test", products=_make_products(3))
        errors = validate_request(req)
        self.assertTrue(any("5 products" in e for e in errors))

    def test_duplicate_rank(self):
        products = _make_products()
        products[1].rank = 1  # duplicate rank 1
        req = ScriptRequest(niche="test", products=products)
        errors = validate_request(req)
        self.assertTrue(any("Duplicate rank" in e for e in errors))

    def test_invalid_charismatic_type(self):
        req = ScriptRequest(
            niche="test",
            products=_make_products(),
            charismatic_type="bad_type",
        )
        errors = validate_request(req)
        self.assertTrue(any("charismatic_type" in e for e in errors))

    def test_valid_charismatic_types(self):
        for ct in ("reality_check", "micro_humor", "micro_comparison"):
            req = ScriptRequest(niche="test", products=_make_products(), charismatic_type=ct)
            self.assertEqual(validate_request(req), [], f"Type {ct!r} should be valid")

    def test_product_without_name(self):
        products = _make_products()
        products[2].name = ""
        req = ScriptRequest(niche="test", products=products)
        errors = validate_request(req)
        self.assertTrue(any("no name" in e for e in errors))


# ===================================================================
# Script validation
# ===================================================================


class TestValidateScript(unittest.TestCase):

    def test_valid_script_passes(self):
        output = _make_valid_output()
        errors = validate_script(output)
        self.assertEqual(errors, [], f"Expected no errors, got: {errors}")

    def test_total_word_count_computed(self):
        output = _make_valid_output()
        validate_script(output)
        self.assertGreater(output.total_word_count, 0)
        self.assertGreater(output.estimated_duration_min, 0)

    # --- Word count ---

    def test_script_too_short(self):
        output = _make_valid_output()
        # Replace all product sections with tiny content
        for s in output.sections:
            if s.section_type.startswith("product_"):
                s.content = "Short. However minor issue."
                s.word_count = len(s.content.split())
        errors = validate_script(output)
        self.assertTrue(any("too short" in e.lower() for e in errors))

    def test_script_too_long(self):
        output = _make_valid_output()
        for s in output.sections:
            if s.section_type.startswith("product_"):
                s.content = _filler(500) + " however minor issue"
                s.word_count = len(s.content.split())
        errors = validate_script(output)
        self.assertTrue(any("too long" in e.lower() for e in errors))

    # --- Hook ---

    def test_hook_too_short(self):
        output = _make_valid_output()
        output.sections[0] = ScriptSection(section_type="hook", content=_filler(50))
        errors = validate_script(output)
        self.assertTrue(any("hook too short" in e.lower() for e in errors))

    def test_hook_too_long(self):
        output = _make_valid_output()
        output.sections[0] = ScriptSection(section_type="hook", content=_filler(200))
        errors = validate_script(output)
        self.assertTrue(any("hook too long" in e.lower() for e in errors))

    # --- Product section ---

    def test_product_section_too_short(self):
        output = _make_valid_output()
        output.sections[2] = ScriptSection(
            section_type="product_5",
            content="Too short. However minor issue.",
        )
        errors = validate_script(output)
        self.assertTrue(any("product_5 too short" in e.lower() for e in errors))

    # --- Retention reset ---

    def test_retention_reset_too_short(self):
        output = _make_valid_output()
        output.sections[5] = ScriptSection(section_type="retention_reset", content=_filler(20))
        errors = validate_script(output)
        self.assertTrue(any("retention reset too short" in e.lower() for e in errors))

    def test_retention_reset_too_long(self):
        output = _make_valid_output()
        output.sections[5] = ScriptSection(section_type="retention_reset", content=_filler(120))
        errors = validate_script(output)
        self.assertTrue(any("retention reset too long" in e.lower() for e in errors))

    # --- Section order ---

    def test_wrong_section_order(self):
        output = _make_valid_output()
        # Swap hook and avatar_intro
        output.sections[0], output.sections[1] = output.sections[1], output.sections[0]
        errors = validate_script(output)
        self.assertTrue(any("section order" in e.lower() for e in errors))

    # --- Avatar intro ---

    def test_avatar_intro_too_long(self):
        output = _make_valid_output()
        output.avatar_intro = "x" * (AVATAR_INTRO_MAX_CHARS + 1)
        errors = validate_script(output)
        self.assertTrue(any("avatar intro too long" in e.lower() for e in errors))

    def test_avatar_intro_missing(self):
        output = _make_valid_output()
        output.avatar_intro = ""
        errors = validate_script(output)
        self.assertTrue(any("avatar intro is required" in e.lower() for e in errors))

    # --- Thumbnail headlines ---

    def test_thumbnail_headline_too_long(self):
        output = _make_valid_output()
        output.thumbnail_headlines = ["This Has Way Too Many Words Here", "OK", "Fine"]
        errors = validate_script(output)
        self.assertTrue(any("thumbnail headline" in e.lower() for e in errors))

    def test_too_few_headlines(self):
        output = _make_valid_output()
        output.thumbnail_headlines = ["One", "Two"]
        errors = validate_script(output)
        self.assertTrue(any("3 thumbnail" in e.lower() for e in errors))

    # --- Language rules ---

    def test_hype_words_detected(self):
        output = _make_valid_output()
        output.sections[0] = ScriptSection(
            section_type="hook",
            content="This product is absolutely insane and crazy good " + _filler(100),
        )
        errors = validate_script(output)
        self.assertTrue(any("hype words" in e.lower() for e in errors))

    def test_ai_cliches_detected(self):
        output = _make_valid_output()
        output.sections[0] = ScriptSection(
            section_type="hook",
            content="When it comes to test niche in today's fast-paced world " + _filler(100),
        )
        errors = validate_script(output)
        self.assertTrue(any("ai cliche" in e.lower() for e in errors))

    # --- Compliance ---

    def test_compliance_violation_detected(self):
        output = _make_valid_output()
        output.sections[0] = ScriptSection(
            section_type="hook",
            content="As an official Amazon partner I can confirm this is a limited time only deal " + _filler(80),
        )
        errors = validate_script(output)
        self.assertTrue(any("compliance" in e.lower() for e in errors))

    def test_missing_affiliate_disclosure(self):
        output = _make_valid_output()
        # Replace conclusion with one that has no disclosure
        output.sections[-1] = ScriptSection(
            section_type="conclusion",
            content="Thanks for watching. See you next time. " + _filler(30),
        )
        errors = validate_script(output)
        self.assertTrue(any("disclosure" in e.lower() for e in errors))

    # --- Downside check ---

    def test_product_missing_downside(self):
        output = _make_valid_output()
        # Replace product_5 with no downside markers
        output.sections[2] = ScriptSection(
            section_type="product_5",
            content="This product is great. It has many features. " + _filler(230),
        )
        errors = validate_script(output)
        self.assertTrue(any("product_5" in e.lower() and "downside" in e.lower() for e in errors))


# ===================================================================
# Prompt builders
# ===================================================================


class TestPromptBuilders(unittest.TestCase):

    def test_extraction_prompt_includes_niche(self):
        prompt = build_extraction_prompt(["https://youtube.com/watch?v=abc"], "test niche")
        self.assertIn("test niche", prompt)
        self.assertIn("https://youtube.com/watch?v=abc", prompt)

    def test_extraction_prompt_no_urls(self):
        prompt = build_extraction_prompt([], "desk accessories")
        self.assertIn("desk accessories", prompt)
        self.assertIn("no references provided", prompt)

    def test_draft_prompt_includes_products(self):
        req = ScriptRequest(
            niche="test niche",
            products=[
                ProductEntry(rank=5, name="Product A", positioning="budget pick"),
                ProductEntry(rank=4, name="Product B"),
                ProductEntry(rank=3, name="Product C"),
                ProductEntry(rank=2, name="Product D"),
                ProductEntry(rank=1, name="Product E", positioning="best overall"),
            ],
        )
        prompt = build_draft_prompt(req, "some viral patterns here")
        self.assertIn("Product A", prompt)
        self.assertIn("Product E", prompt)
        self.assertIn("budget pick", prompt)
        self.assertIn("best overall", prompt)
        self.assertIn(str(SCRIPT_WORD_MIN), prompt)
        self.assertIn(str(SCRIPT_WORD_MAX), prompt)

    def test_refinement_prompt_includes_charismatic(self):
        prompt = build_refinement_prompt("draft text here", "micro_humor")
        self.assertIn("humor", prompt.lower())
        self.assertIn("draft text here", prompt)

    def test_refinement_prompt_reality_check(self):
        prompt = build_refinement_prompt("draft", "reality_check")
        self.assertIn("reality check", prompt.lower())

    def test_refinement_prompt_micro_comparison(self):
        prompt = build_refinement_prompt("draft", "micro_comparison")
        self.assertIn("comparison", prompt.lower())


if __name__ == "__main__":
    unittest.main()
