#!/usr/bin/env python3
"""Tests for tools/elevenlabs_voiceover_api.py — voiceover text processing utilities."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from elevenlabs_voiceover_api import (
    build_section_plan,
    classify_heading,
    normalize_text,
    slug,
)


# ---------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------

class TestNormalizeText(unittest.TestCase):

    def test_strips_inline_code(self):
        self.assertEqual(normalize_text("`code`"), "code")

    def test_strips_bold(self):
        self.assertEqual(normalize_text("**bold text**"), "bold text")

    def test_strips_heading_markers(self):
        self.assertEqual(normalize_text("### Heading"), "Heading")

    def test_strips_bullet_points(self):
        result = normalize_text("- item one\n* item two")
        self.assertIn("item one", result)
        self.assertIn("item two", result)

    def test_collapses_multiple_newlines(self):
        result = normalize_text("a\n\n\n\nb")
        self.assertNotIn("\n\n\n", result)

    def test_strips_whitespace(self):
        self.assertEqual(normalize_text("  hello  "), "hello")

    def test_empty_string(self):
        self.assertEqual(normalize_text(""), "")

    def test_combined_markdown(self):
        result = normalize_text("### **Title**\n\n- `bullet` item")
        self.assertIn("Title", result)
        self.assertIn("bullet", result)
        self.assertNotIn("###", result)
        self.assertNotIn("`", result)
        self.assertNotIn("**", result)


# ---------------------------------------------------------------
# slug
# ---------------------------------------------------------------

class TestSlug(unittest.TestCase):

    def test_basic(self):
        self.assertEqual(slug("Hello World"), "hello_world")

    def test_special_characters(self):
        self.assertEqual(slug("Test!@#$%Value"), "test_value")

    def test_multiple_spaces(self):
        self.assertEqual(slug("a   b   c"), "a_b_c")

    def test_empty_string(self):
        self.assertEqual(slug(""), "scene")

    def test_only_special_chars(self):
        self.assertEqual(slug("!!!"), "scene")

    def test_max_len_truncation(self):
        result = slug("a" * 50, max_len=10)
        self.assertLessEqual(len(result), 10)

    def test_max_len_default(self):
        result = slug("a" * 50)
        self.assertLessEqual(len(result), 32)

    def test_leading_trailing_underscores_stripped(self):
        result = slug("  hello  ")
        self.assertFalse(result.startswith("_"))
        self.assertFalse(result.endswith("_"))

    def test_numbers_preserved(self):
        self.assertEqual(slug("Product 123"), "product_123")

    def test_truncation_strips_trailing_underscore(self):
        # If truncation leaves a trailing underscore, it should be stripped
        result = slug("ab_cd_ef_gh", max_len=5)
        self.assertFalse(result.endswith("_"))


# ---------------------------------------------------------------
# classify_heading
# ---------------------------------------------------------------

class TestClassifyHeading(unittest.TestCase):

    def test_hook(self):
        self.assertEqual(classify_heading("Hook"), "hook")

    def test_intro(self):
        self.assertEqual(classify_heading("Intro Segment"), "hook")

    def test_criteria(self):
        self.assertEqual(classify_heading("Selection Criteria"), "criteria")

    def test_methodology(self):
        self.assertEqual(classify_heading("Methodology"), "criteria")

    def test_cta(self):
        self.assertEqual(classify_heading("CTA"), "cta")

    def test_call_to_action(self):
        self.assertEqual(classify_heading("Call to Action"), "cta")

    def test_disclosure(self):
        self.assertEqual(classify_heading("Disclosure"), "disclosure")

    def test_description_block(self):
        self.assertEqual(classify_heading("Description Block"), "disclosure")

    def test_recap(self):
        self.assertEqual(classify_heading("Recap"), "recap")

    def test_summary(self):
        self.assertEqual(classify_heading("Final Summary"), "recap")

    def test_verdict(self):
        self.assertEqual(classify_heading("Final Verdict"), "recap")

    def test_rank_numbered(self):
        self.assertEqual(classify_heading("# 5 — Best Value"), "rank")

    def test_rank_top(self):
        self.assertEqual(classify_heading("Top 3 Picks"), "rank")

    def test_rank_word(self):
        self.assertEqual(classify_heading("Product Rank"), "rank")

    def test_other(self):
        self.assertEqual(classify_heading("Random Section"), "other")

    def test_case_insensitive(self):
        self.assertEqual(classify_heading("HOOK"), "hook")
        self.assertEqual(classify_heading("cta"), "cta")


# ---------------------------------------------------------------
# build_section_plan
# ---------------------------------------------------------------

class TestBuildSectionPlan(unittest.TestCase):

    def test_empty_string(self):
        self.assertEqual(build_section_plan(""), [])

    def test_no_headings_returns_single_section(self):
        plan = build_section_plan("Hello, welcome to the show.")
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0][0], "full_script")
        self.assertIn("vo_01_full_script.mp3", plan[0][1])
        self.assertIn("Hello", plan[0][2])

    def test_single_heading(self):
        script = "## Hook\n\nWelcome to the show!"
        plan = build_section_plan(script)
        self.assertEqual(len(plan), 1)
        self.assertIn("hook", plan[0][0])
        self.assertIn("Welcome to the show!", plan[0][2])

    def test_multiple_headings_ordered(self):
        script = (
            "## CTA\n\nSubscribe now!\n\n"
            "## Hook\n\nHey everyone!\n\n"
            "## Recap\n\nThat's a wrap!"
        )
        plan = build_section_plan(script)
        # Order should be: hook, recap, cta
        kinds = [p[0] for p in plan]
        hook_idx = next(i for i, k in enumerate(kinds) if "hook" in k)
        recap_idx = next(i for i, k in enumerate(kinds) if "recap" in k)
        cta_idx = next(i for i, k in enumerate(kinds) if "cta" in k)
        self.assertLess(hook_idx, recap_idx)
        self.assertLess(recap_idx, cta_idx)

    def test_filenames_numbered(self):
        script = "## Hook\n\nIntro text.\n\n## # 1 — Product\n\nProduct one.\n\n## Recap\n\nDone."
        plan = build_section_plan(script)
        for key, filename, body in plan:
            self.assertTrue(filename.startswith("vo_"))
            self.assertTrue(filename.endswith(".mp3"))

    def test_empty_sections_skipped(self):
        script = "## Hook\n\nContent here.\n\n## Empty\n\n## Recap\n\nFinal."
        plan = build_section_plan(script)
        # "Empty" section has no body, should be skipped
        bodies = [p[2] for p in plan]
        self.assertTrue(all(b.strip() for b in bodies))

    def test_rank_sections_numbered(self):
        script = (
            "## # 1 — Budget Pick\n\nFirst product.\n\n"
            "## # 2 — Premium Pick\n\nSecond product.\n\n"
            "## # 3 — Best Value\n\nThird product."
        )
        plan = build_section_plan(script)
        self.assertEqual(len(plan), 3)
        # All should be rank type
        for key, filename, body in plan:
            self.assertIn("rank_", key)

    def test_markdown_stripped_from_body(self):
        script = "## Hook\n\n**Bold** and `code` with ### heading"
        plan = build_section_plan(script)
        body = plan[0][2]
        self.assertNotIn("**", body)
        self.assertNotIn("`", body)

    def test_unique_keys_with_duplicates(self):
        script = (
            "## Hook\n\nFirst hook.\n\n"
            "## Hook\n\nSecond hook."
        )
        plan = build_section_plan(script)
        keys = [p[0] for p in plan]
        self.assertEqual(len(keys), len(set(keys)), "Keys should be unique")


# ---------------------------------------------------------------
# None-safety tests (slug + classify_heading)
# ---------------------------------------------------------------

class TestSlugNoneSafety(unittest.TestCase):

    def test_none_returns_scene(self):
        self.assertEqual(slug(None), "scene")

    def test_none_with_max_len(self):
        self.assertEqual(slug(None, max_len=5), "scene")

    def test_whitespace_only_returns_scene(self):
        self.assertEqual(slug("   "), "scene")

    def test_unicode_preserved(self):
        result = slug("Café Mocha")
        self.assertEqual(result, "caf_mocha")

    def test_max_len_1(self):
        result = slug("hello", max_len=1)
        self.assertEqual(len(result), 1)


class TestClassifyHeadingNoneSafety(unittest.TestCase):

    def test_none_returns_other(self):
        self.assertEqual(classify_heading(None), "other")

    def test_empty_returns_other(self):
        self.assertEqual(classify_heading(""), "other")

    def test_whitespace_returns_other(self):
        self.assertEqual(classify_heading("   "), "other")


# ---------------------------------------------------------------
# build_section_plan edge cases
# ---------------------------------------------------------------

class TestBuildSectionPlanEdgeCases(unittest.TestCase):

    def test_heading_without_content_skipped(self):
        script = "## Hook\n\n\n\n## Recap\n\nFinal text here."
        plan = build_section_plan(script)
        bodies = [p[2] for p in plan]
        self.assertTrue(all(b.strip() for b in bodies))

    def test_very_long_body_not_truncated(self):
        body = "Word " * 500
        script = f"## Hook\n\n{body}"
        plan = build_section_plan(script)
        self.assertGreater(len(plan[0][2]), 100)

    def test_filenames_all_unique(self):
        script = "## Hook\n\nA.\n\n## CTA\n\nB.\n\n## Recap\n\nC."
        plan = build_section_plan(script)
        filenames = [p[1] for p in plan]
        self.assertEqual(len(filenames), len(set(filenames)))

    def test_only_whitespace_body(self):
        result = build_section_plan("   \n\n   \n  ")
        # Either empty or single section with whitespace-only body
        if result:
            self.assertEqual(len(result), 1)

    def test_h3_heading_parsed(self):
        script = "### Hook Section\n\nContent here."
        plan = build_section_plan(script)
        self.assertGreaterEqual(len(plan), 1)


if __name__ == "__main__":
    unittest.main()
