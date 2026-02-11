"""Tests for tools/lib/script_brief.py and pipeline script-brief/script-review.

Covers: generate_brief, review_script, apply_light_fixes, format_review_notes,
        cmd_script_brief, cmd_script_review.
No API calls — pure logic tests.
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

from tools.lib.script_brief import (
    ReviewIssue,
    apply_light_fixes,
    format_review_notes,
    generate_brief,
    review_script,
)
from tools.lib.video_paths import VideoPaths


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_PRODUCTS = {
    "keyword": "wireless earbuds",
    "niche": "wireless earbuds",
    "sources_used": ["Wirecutter", "RTINGS", "PCMag"],
    "products": [
        {
            "rank": r,
            "name": f"Product {r}",
            "brand": f"Brand{r}",
            "positioning": f"best for rank {r}",
            "price": f"${r * 50}.99",
            "rating": "4.5",
            "benefits": [f"Benefit A for {r}", f"Benefit B for {r}"],
            "downside": f"Minor issue with product {r}",
            "evidence": [
                {
                    "source": "Wirecutter",
                    "label": "top pick" if r == 1 else "",
                    "reasons": [
                        f"Wirecutter measured {r * 10} dB noise isolation",
                        f"Comfortable fit for product {r}",
                    ],
                },
                {
                    "source": "RTINGS",
                    "reasons": [f"RTINGS rated product {r} at {r * 8}/10"],
                },
            ],
            "key_claims": [f"Best in class for rank {r}"],
        }
        for r in [5, 4, 3, 2, 1]
    ],
}

SAMPLE_SEO = {
    "primary_keyword": "best wireless earbuds 2025",
    "secondary_keywords": ["top earbuds", "wireless earbuds review", "earbuds comparison"],
}

# A valid script that should pass review
VALID_SCRIPT = """[HOOK]
""" + " ".join(["word"] * 120) + """
You spent hours reading reviews. Half are fake. Here's what the real experts say about wireless earbuds.

[AVATAR_INTRO]
I'm Ray, and I test products so you don't have to.

[PRODUCT_5]
""" + " ".join(["word"] * 220) + """
Starting at number five. According to Wirecutter, this one measured 50 dB noise isolation.
The comfort is outstanding for long sessions. However, the bass can be muddy at high volumes.

[PRODUCT_4]
""" + " ".join(["word"] * 220) + """
At number four. RTINGS rated this at 32 out of 10. Great value pick.
That said, the touch controls take some getting used to.

[PRODUCT_3]
""" + " ".join(["word"] * 220) + """
Number three. Wirecutter's top pick for most people. The sound is balanced.
Keep in mind, the case is larger than competitors.

[RETENTION_RESET]
""" + " ".join(["word"] * 60) + """
Quick question — have you ever returned earbuds because they didn't fit?

[PRODUCT_2]
""" + " ".join(["word"] * 220) + """
Number two. RTINGS measured the best noise cancellation in this price range.
One drawback: battery life is only 5 hours.

[PRODUCT_1]
""" + " ".join(["word"] * 220) + """
And number one. The expert consensus pick. Wirecutter and RTINGS both agree.
The trade-off is the premium price tag.

[CONCLUSION]
Links to all five are in the description. Those are affiliate links, which means
I may earn a small commission at no extra cost to you.
"""


# ---------------------------------------------------------------------------
# Tests: generate_brief
# ---------------------------------------------------------------------------


class TestGenerateBrief(unittest.TestCase):
    """Test brief generation from product data."""

    def test_contains_niche(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        self.assertIn("WIRELESS EARBUDS", brief.upper())

    def test_contains_primary_keyword_from_seo(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, SAMPLE_SEO)
        self.assertIn("best wireless earbuds 2025", brief)

    def test_contains_secondary_keywords(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, SAMPLE_SEO)
        self.assertIn("top earbuds", brief)

    def test_derives_keywords_without_seo(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        self.assertIn("best wireless earbuds", brief)

    def test_contains_word_count_target(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        self.assertIn("1300", brief)
        self.assertIn("1800", brief)

    def test_contains_hook_suggestions(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        self.assertIn("Problem hook", brief)
        self.assertIn("Contrarian hook", brief)

    def test_contains_all_products(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        for r in [1, 2, 3, 4, 5]:
            self.assertIn(f"Product #{r}", brief)

    def test_contains_evidence(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        self.assertIn("Wirecutter", brief)
        self.assertIn("RTINGS", brief)

    def test_contains_benefits(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        self.assertIn("Benefit A for 1", brief)

    def test_contains_downside(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        self.assertIn("Minor issue with product 1", brief)

    def test_contains_retention_reset(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        self.assertIn("[RETENTION_RESET]", brief)

    def test_contains_disclosure_reminder(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        self.assertIn("affiliate", brief.lower())
        self.assertIn("commission", brief.lower())
        self.assertIn("no extra cost", brief.lower())

    def test_contains_tone_guidance(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        self.assertIn("Energetic but trustworthy", brief)

    def test_contains_signature_moment(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        self.assertIn("Signature moment", brief)

    def test_contains_pattern_interrupt(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        self.assertIn("Pattern interrupt", brief)

    def test_contains_source_attribution_notes(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        self.assertIn("Source attribution", brief)

    def test_contains_next_steps(self):
        brief = generate_brief("wireless earbuds", SAMPLE_PRODUCTS, {})
        self.assertIn("script_raw.txt", brief)
        self.assertIn("script-review", brief)


# ---------------------------------------------------------------------------
# Tests: review_script
# ---------------------------------------------------------------------------


class TestReviewScript(unittest.TestCase):
    """Test script review validation."""

    def test_valid_script_passes(self):
        result = review_script(VALID_SCRIPT, SAMPLE_PRODUCTS)
        # May have warnings but no errors about word count or missing sections
        errors = [i for i in result.errors if "Missing section" in i.message or "too short" in i.message.lower()]
        self.assertEqual(len(errors), 0, f"Unexpected errors: {[i.message for i in errors]}")

    def test_too_short(self):
        result = review_script("[HOOK]\nShort script.\n[CONCLUSION]\nBye.", SAMPLE_PRODUCTS)
        error_msgs = [i.message for i in result.errors]
        self.assertTrue(any("too short" in m.lower() or "Too short" in m for m in error_msgs))

    def test_missing_sections(self):
        result = review_script("[HOOK]\nSome text here.\n[CONCLUSION]\nDone.", SAMPLE_PRODUCTS)
        error_msgs = [i.message for i in result.errors]
        self.assertTrue(any("Missing section" in m for m in error_msgs))

    def test_missing_disclosure(self):
        script = VALID_SCRIPT.replace("affiliate", "link").replace("commission", "").replace("no extra cost", "")
        result = review_script(script, SAMPLE_PRODUCTS)
        error_msgs = [i.message for i in result.errors]
        self.assertTrue(any("disclosure" in m.lower() for m in error_msgs))

    def test_hype_words_flagged(self):
        script = VALID_SCRIPT.replace("outstanding", "insane")
        result = review_script(script, SAMPLE_PRODUCTS)
        all_msgs = [i.message for i in result.issues]
        self.assertTrue(any("Hype" in m or "hype" in m for m in all_msgs))

    def test_missing_downside_flagged(self):
        # Remove all downside language from product_5
        script = VALID_SCRIPT.replace("However, the bass can be muddy at high volumes.", "The bass is great.")
        result = review_script(script, SAMPLE_PRODUCTS)
        self.assertTrue(any(
            "downside" in i.message.lower() and i.section == "product_5"
            for i in result.issues
        ))

    def test_spec_not_in_evidence_warned(self):
        # Add a made-up spec
        script = VALID_SCRIPT + "\nThis product achieves 999 dB noise isolation.\n"
        result = review_script(script, SAMPLE_PRODUCTS)
        warnings = [i for i in result.warnings if "999" in i.message]
        self.assertGreater(len(warnings), 0)

    def test_section_word_counts_populated(self):
        result = review_script(VALID_SCRIPT, SAMPLE_PRODUCTS)
        self.assertIn("hook", result.section_word_counts)
        self.assertIn("conclusion", result.section_word_counts)

    def test_word_count_populated(self):
        result = review_script(VALID_SCRIPT, SAMPLE_PRODUCTS)
        self.assertGreater(result.word_count, 0)

    def test_estimated_duration(self):
        result = review_script(VALID_SCRIPT, SAMPLE_PRODUCTS)
        self.assertGreater(result.estimated_duration_min, 0)


# ---------------------------------------------------------------------------
# Tests: apply_light_fixes
# ---------------------------------------------------------------------------


class TestApplyLightFixes(unittest.TestCase):

    def test_collapses_double_spaces(self):
        text, changes = apply_light_fixes("hello  world")
        self.assertNotIn("  ", text)
        self.assertTrue(any("double spaces" in c.lower() for c in changes))

    def test_removes_trailing_whitespace(self):
        text, changes = apply_light_fixes("hello   \nworld   ")
        self.assertFalse(any(line.endswith(" ") for line in text.splitlines()))

    def test_removes_ai_cliches(self):
        text, changes = apply_light_fixes("When it comes to wireless earbuds, they are great.")
        self.assertNotIn("when it comes to", text.lower())
        self.assertTrue(any("cliche" in c.lower() for c in changes))

    def test_no_changes_on_clean_text(self):
        text, changes = apply_light_fixes("Clean text with no issues.")
        self.assertEqual(len(changes), 0)

    def test_collapses_excess_blank_lines(self):
        text, changes = apply_light_fixes("line 1\n\n\n\n\nline 2")
        self.assertNotIn("\n\n\n", text)


# ---------------------------------------------------------------------------
# Tests: format_review_notes
# ---------------------------------------------------------------------------


class TestFormatReviewNotes(unittest.TestCase):

    def test_contains_verdict(self):
        result = review_script(VALID_SCRIPT, SAMPLE_PRODUCTS)
        notes = format_review_notes(result, "test-001")
        self.assertIn("Verdict:", notes)

    def test_contains_word_count(self):
        result = review_script(VALID_SCRIPT, SAMPLE_PRODUCTS)
        notes = format_review_notes(result, "test-001")
        self.assertIn(str(result.word_count), notes)


# ---------------------------------------------------------------------------
# Tests: pipeline integration
# ---------------------------------------------------------------------------


class TestPipelineScriptBrief(unittest.TestCase):
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

    def _setup_video(self, video_id, niche="wireless earbuds"):
        from tools.lib.pipeline_status import start_pipeline
        paths = VideoPaths(video_id)
        paths.ensure_dirs()
        start_pipeline(video_id)
        paths.niche_txt.write_text(niche + "\n", encoding="utf-8")
        paths.products_json.write_text(json.dumps(SAMPLE_PRODUCTS), encoding="utf-8")
        return paths

    def test_brief_generates_file(self):
        import argparse
        from tools.pipeline import cmd_script_brief

        paths = self._setup_video("test-brief")
        args = argparse.Namespace(video_id="test-brief")
        result = cmd_script_brief(args)

        self.assertEqual(result, 0)
        self.assertTrue(paths.manual_brief.is_file())
        content = paths.manual_brief.read_text()
        self.assertIn("WIRELESS EARBUDS", content.upper())
        self.assertIn("Product #1", content)

    def test_brief_with_seo_json(self):
        import argparse
        from tools.pipeline import cmd_script_brief

        paths = self._setup_video("test-brief-seo")
        paths.seo_json.write_text(json.dumps(SAMPLE_SEO), encoding="utf-8")
        args = argparse.Namespace(video_id="test-brief-seo")
        result = cmd_script_brief(args)

        self.assertEqual(result, 0)
        content = paths.manual_brief.read_text()
        self.assertIn("best wireless earbuds 2025", content)

    def test_brief_missing_products(self):
        import argparse
        from tools.pipeline import cmd_script_brief

        paths = VideoPaths("test-brief-nop")
        paths.ensure_dirs()
        paths.niche_txt.write_text("earbuds\n", encoding="utf-8")
        # No products.json

        args = argparse.Namespace(video_id="test-brief-nop")
        result = cmd_script_brief(args)
        self.assertEqual(result, 2)  # ACTION_REQUIRED


class TestPipelineScriptReview(unittest.TestCase):
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

    def _setup_video(self, video_id, script_text=VALID_SCRIPT):
        from tools.lib.pipeline_status import start_pipeline
        paths = VideoPaths(video_id)
        paths.ensure_dirs()
        start_pipeline(video_id)
        paths.niche_txt.write_text("wireless earbuds\n", encoding="utf-8")
        paths.products_json.write_text(json.dumps(SAMPLE_PRODUCTS), encoding="utf-8")
        paths.script_raw.parent.mkdir(parents=True, exist_ok=True)
        paths.script_raw.write_text(script_text, encoding="utf-8")
        return paths

    def test_review_generates_notes(self):
        import argparse
        from tools.pipeline import cmd_script_review

        paths = self._setup_video("test-review")
        args = argparse.Namespace(video_id="test-review")
        result = cmd_script_review(args)

        self.assertTrue(paths.script_review_notes.is_file())
        self.assertTrue(paths.script_final.is_file())

    def test_review_generates_script_final(self):
        import argparse
        from tools.pipeline import cmd_script_review

        paths = self._setup_video("test-review-final")
        args = argparse.Namespace(video_id="test-review-final")
        cmd_script_review(args)

        self.assertTrue(paths.script_final.is_file())
        content = paths.script_final.read_text()
        self.assertIn("[HOOK]", content)

    def test_review_missing_script_raw(self):
        import argparse
        from tools.pipeline import cmd_script_review

        paths = VideoPaths("test-review-nop")
        paths.ensure_dirs()

        args = argparse.Namespace(video_id="test-review-nop")
        result = cmd_script_review(args)
        self.assertEqual(result, 2)  # ACTION_REQUIRED

    def test_review_bad_script_returns_action_required(self):
        import argparse
        from tools.pipeline import cmd_script_review

        paths = self._setup_video("test-review-bad", script_text="[HOOK]\nToo short.\n[CONCLUSION]\nBye.")
        args = argparse.Namespace(video_id="test-review-bad")
        result = cmd_script_review(args)
        self.assertEqual(result, 2)  # ACTION_REQUIRED (errors found)


if __name__ == "__main__":
    unittest.main()
