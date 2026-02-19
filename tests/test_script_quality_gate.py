#!/usr/bin/env python3
"""Tests for script_quality_gate.py — anti-AI checks, conversion structure, rhythm, scoring."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Ensure tools/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from script_quality_gate import (
    _normalize,
    _sentence_lengths,
    _split_product_sections,
    check_claims_without_sources,
    check_contraction_usage,
    check_conversion_structure,
    check_em_dash_overuse,
    check_rhythm,
    check_rule_of_three,
    evaluate_script_quality,
    find_ai_vocabulary,
    find_phrase_violations,
    find_structural_violations,
    load_banned_phrases,
    write_quality_report,
    DEFAULT_BANNED_PHRASES,
    AI_VOCABULARY,
    SHORT_PUNCH_MAX_WORDS,
)


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------

class TestNormalize(unittest.TestCase):
    def test_lowercase(self):
        self.assertEqual(_normalize("Hello World"), "hello world")

    def test_curly_quotes(self):
        self.assertEqual(_normalize("it\u2019s"), "it's")

    def test_hyphens_to_spaces(self):
        self.assertEqual(_normalize("game-changer"), "game changer")

    def test_multiple_spaces(self):
        self.assertEqual(_normalize("too   many   spaces"), "too many spaces")

    def test_empty(self):
        self.assertEqual(_normalize(""), "")

    def test_none(self):
        self.assertEqual(_normalize(None), "")


# ---------------------------------------------------------------------------
# load_banned_phrases
# ---------------------------------------------------------------------------

class TestLoadBannedPhrases(unittest.TestCase):
    def test_includes_defaults(self):
        phrases = load_banned_phrases()
        self.assertTrue(len(phrases) >= len(DEFAULT_BANNED_PHRASES))

    def test_default_phrases_present(self):
        phrases = load_banned_phrases()
        norm = [_normalize(p) for p in phrases]
        self.assertIn("without further ado", norm)
        self.assertIn("let's dive in", norm)
        self.assertIn("game changer", norm)


# ---------------------------------------------------------------------------
# find_phrase_violations
# ---------------------------------------------------------------------------

class TestFindPhraseViolations(unittest.TestCase):
    def test_detects_banned_phrase(self):
        text = "Without further ado, let's start the review."
        violations = find_phrase_violations(text, DEFAULT_BANNED_PHRASES)
        self.assertTrue(any(v["type"] == "banned_phrase" for v in violations))

    def test_case_insensitive(self):
        text = "Let's Dive In to this product review!"
        violations = find_phrase_violations(text, DEFAULT_BANNED_PHRASES)
        self.assertTrue(any(v["type"] == "banned_phrase" for v in violations))

    def test_clean_text_no_violations(self):
        text = "This keyboard has a solid build and responsive keys."
        violations = find_phrase_violations(text, DEFAULT_BANNED_PHRASES)
        self.assertEqual(violations, [])

    def test_multiple_violations(self):
        text = "Without further ado, this game-changer is a must-buy.\nIt's worth noting the sleek design."
        violations = find_phrase_violations(text, DEFAULT_BANNED_PHRASES)
        self.assertGreaterEqual(len(violations), 2)

    def test_severity_is_high(self):
        text = "Let's dive right in to the features."
        violations = find_phrase_violations(text, DEFAULT_BANNED_PHRASES)
        for v in violations:
            self.assertEqual(v["severity"], "HIGH")

    def test_includes_line_number(self):
        text = "Line one.\nLine two.\nWithout further ado, here we go."
        violations = find_phrase_violations(text, DEFAULT_BANNED_PHRASES)
        self.assertTrue(any(v["line"] == 3 for v in violations))


# ---------------------------------------------------------------------------
# find_ai_vocabulary
# ---------------------------------------------------------------------------

class TestFindAIVocabulary(unittest.TestCase):
    def test_detects_ai_word(self):
        text = "This product showcases a vibrant landscape of features."
        violations = find_ai_vocabulary(text)
        rules = [v["rule"] for v in violations]
        self.assertIn("vibrant", rules)
        self.assertIn("landscape", rules)

    def test_word_boundary(self):
        # "delve" should match as whole word
        text = "Let's delve into the details."
        violations = find_ai_vocabulary(text)
        self.assertTrue(any(v["rule"] == "delve" for v in violations))

    def test_clean_text(self):
        text = "The keyboard feels good and types well."
        violations = find_ai_vocabulary(text)
        self.assertEqual(violations, [])

    def test_severity_is_medium(self):
        text = "This delve into the intricacies shows pivotal results."
        violations = find_ai_vocabulary(text)
        for v in violations:
            self.assertEqual(v["severity"], "MEDIUM")


# ---------------------------------------------------------------------------
# find_structural_violations
# ---------------------------------------------------------------------------

class TestFindStructuralViolations(unittest.TestCase):
    def test_template_opening(self):
        text = "This product boasts an impressive array of features."
        violations = find_structural_violations(text)
        self.assertTrue(any(v["rule"] == "template_opening" for v in violations))

    def test_ranking_transition(self):
        text = "Coming in at number 3, we have the Logitech MX Keys."
        violations = find_structural_violations(text)
        self.assertTrue(any(v["rule"] == "ranking_transition" for v in violations))

    def test_next_up(self):
        text = "Next up is the Corsair K95."
        violations = find_structural_violations(text)
        self.assertTrue(any(v["rule"] == "next_up" for v in violations))

    def test_moving_on(self):
        text = "Moving on to our third pick."
        violations = find_structural_violations(text)
        self.assertTrue(any(v["rule"] == "moving_on" for v in violations))

    def test_clean_transition(self):
        text = "Now here's something different about the K95."
        violations = find_structural_violations(text)
        self.assertEqual(violations, [])


# ---------------------------------------------------------------------------
# _sentence_lengths / check_rhythm
# ---------------------------------------------------------------------------

class TestSentenceLengths(unittest.TestCase):
    def test_basic_sentences(self):
        text = "One two three. Four five six seven. A b."
        lengths = _sentence_lengths(text)
        self.assertEqual(lengths, [3, 4, 2])  # >= 2 words all counted

    def test_strips_markdown_headers(self):
        text = "## Product Title\nThis is the body. Another sentence here."
        lengths = _sentence_lengths(text)
        # Header should be removed, only body sentences counted
        self.assertTrue(len(lengths) >= 1)


class TestCheckRhythm(unittest.TestCase):
    def test_monotone_flagged(self):
        # 5+ sentences all ~10 words
        text = ". ".join(["word " * 10 for _ in range(6)]) + "."
        violations = check_rhythm(text)
        self.assertTrue(any(v["type"] == "rhythm_monotone" for v in violations))

    def test_varied_rhythm_ok(self):
        text = (
            "Short sentence. "
            "This is a medium-length sentence with more words in it. "
            "Wow. "
            "Here is another longer sentence that should vary the rhythm quite a bit. "
            "Good. "
            "And one more medium sentence here."
        )
        violations = check_rhythm(text)
        self.assertEqual(violations, [])

    def test_only_one_flag(self):
        # Even with many monotone stretches, only one flag
        text = ". ".join(["word " * 8 for _ in range(20)]) + "."
        violations = check_rhythm(text)
        self.assertLessEqual(len(violations), 1)


# ---------------------------------------------------------------------------
# _split_product_sections / check_conversion_structure
# ---------------------------------------------------------------------------

class TestSplitProductSections(unittest.TestCase):
    def test_finds_sections(self):
        text = """## #5 - Logitech MX Keys
This keyboard has great features. It types well and feels solid.
The build quality is excellent overall.

## #4 - Corsair K95
Another great keyboard with many features. RGB lighting is top notch.
The macro keys are incredibly useful.
"""
        sections = _split_product_sections(text)
        self.assertEqual(len(sections), 2)

    def test_skips_recap_section(self):
        text = """## #5 - Product A
Body text goes here for the review section with lots of details.

## Recap / Final Thoughts
This section should be skipped by the parser.
"""
        sections = _split_product_sections(text)
        self.assertEqual(len(sections), 1)

    def test_skips_short_sections(self):
        text = """## #5 - Product A
Short.

## #4 - Product B
This section has enough text to be considered substantive and meaningful for analysis.
"""
        sections = _split_product_sections(text)
        self.assertEqual(len(sections), 1)  # Only B has >50 chars


class TestCheckConversionStructure(unittest.TestCase):
    def test_good_section_passes(self):
        text = """## #5 - Logitech MX Keys
This keyboard is great for typists who want comfort. The keys feel responsive.
However, the price is a drawback for budget buyers.
If you work from home, this is perfect for you.
Not for gamers who need fast response times.
Worth it.
"""
        violations = check_conversion_structure(text)
        # Should have minimal violations since it has critique, who-should, who-shouldnt, short punch
        critique_violations = [v for v in violations if v["type"] == "missing_critique"]
        self.assertEqual(critique_violations, [])

    def test_missing_critique_flagged(self):
        text = """## #5 - Amazing Product
This product is wonderful and perfect in every way. The design is stunning.
Everything about it works flawlessly. If you need a keyboard, get this one.
Skip inferior alternatives.
Loved it!
"""
        violations = check_conversion_structure(text)
        critique_violations = [v for v in violations if v["type"] == "missing_critique"]
        self.assertGreater(len(critique_violations), 0)

    def test_no_sections_flagged(self):
        text = "Just a plain paragraph with no headers at all."
        violations = check_conversion_structure(text)
        self.assertTrue(any(v["type"] == "structure_missing" for v in violations))


# ---------------------------------------------------------------------------
# Style checks
# ---------------------------------------------------------------------------

class TestCheckEmDashOveruse(unittest.TestCase):
    def test_ok_count(self):
        text = "First point — then second — finally third."
        self.assertEqual(check_em_dash_overuse(text), [])

    def test_overuse(self):
        text = "One — two — three — four — five."
        violations = check_em_dash_overuse(text)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["type"], "em_dash_overuse")

    def test_counts_double_hyphens(self):
        text = "One -- two -- three -- four -- five."
        violations = check_em_dash_overuse(text)
        self.assertEqual(len(violations), 1)


class TestCheckRuleOfThree(unittest.TestCase):
    def test_ok_count(self):
        text = "Red, green, and blue are primary colors."
        self.assertEqual(check_rule_of_three(text), [])

    def test_overuse(self):
        text = (
            "It's fast, sleek, and powerful. "
            "Also light, durable, and affordable. "
            "Plus smart, quiet, and efficient."
        )
        violations = check_rule_of_three(text)
        self.assertEqual(len(violations), 1)


class TestCheckContractionUsage(unittest.TestCase):
    def test_good_contraction_rate(self):
        text = "It's great. Don't miss it. You'll love this. That's the truth."
        self.assertEqual(check_contraction_usage(text), [])

    def test_formal_tone_flagged(self):
        text = "It is wonderful. Do not miss it. You will enjoy this. That is certain. Does not disappoint. Can not fail."
        violations = check_contraction_usage(text)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["type"], "low_contraction_rate")

    def test_no_contractions_at_all(self):
        text = "The product works. Buy one today."
        # No contraction opportunities = no violations
        self.assertEqual(check_contraction_usage(text), [])


# ---------------------------------------------------------------------------
# check_claims_without_sources
# ---------------------------------------------------------------------------

class TestCheckClaimsWithoutSources(unittest.TestCase):
    def test_claim_with_source_ok(self):
        text = "This is the best keyboard according to Wirecutter reviews."
        violations = check_claims_without_sources(text)
        self.assertEqual(violations, [])

    def test_unsourced_claim_flagged(self):
        text = "This is the ultimate gaming experience ever created."
        violations = check_claims_without_sources(text)
        self.assertTrue(any(v["type"] == "claim_without_source" for v in violations))

    def test_nearby_source_counts(self):
        text = "The study shows impressive results.\nThis is the best option.\nBased on testing, it works."
        violations = check_claims_without_sources(text)
        # "best" on line 2 should find "study" on line 1 and "testing" on line 3
        claim_violations = [v for v in violations if "best" in v.get("excerpt", "").lower()]
        self.assertEqual(claim_violations, [])

    def test_max_10_violations(self):
        # Generate many claims
        text = "\n".join(f"This is the ultimate product {i}." for i in range(20))
        violations = check_claims_without_sources(text)
        self.assertLessEqual(len(violations), 10)


# ---------------------------------------------------------------------------
# evaluate_script_quality
# ---------------------------------------------------------------------------

class TestEvaluateScriptQuality(unittest.TestCase):
    def test_clean_script_passes(self):
        text = """## #5 - Logitech MX Keys
This keyboard is a solid choice for remote workers. The low-profile keys feel comfortable.
However, it's heavier than expected and the price is a drawback.
If you type all day, this one's for you. Great for writers too.
Not for gamers or those on a tight budget. Skip it if you want wireless only.
Worth it.

## #4 - Corsair K95
Here's a different keyboard built for gamers. Mechanical switches feel satisfying.
But the noise level is an issue in shared offices. It lacks Bluetooth.
Best for competitive gamers who need macro keys.
Not ideal for quiet office environments. Avoid if noise bothers you.
Solid pick.
"""
        result = evaluate_script_quality(text, max_violations=5)
        self.assertIn("pass", result)
        self.assertIn("score", result)
        self.assertIn("violations", result)

    def test_ai_heavy_script_fails(self):
        text = """Without further ado, let's dive in to this game-changer!
This product boasts an impressive array of features. Coming in at number 5.
It's a testament to modern engineering. The vibrant landscape of technology
offers a seamless experience. Next up is our fourth pick. Moving on to the third.
"""
        result = evaluate_script_quality(text, max_violations=0)
        self.assertFalse(result["pass"])
        self.assertGreater(result["high_count"], 0)

    def test_result_structure(self):
        text = "Simple clean text."
        result = evaluate_script_quality(text)
        required_keys = {"pass", "score", "max_violations", "high_count",
                         "medium_count", "low_count", "total_violations",
                         "unique_rules", "checks", "violations"}
        self.assertTrue(required_keys.issubset(result.keys()))

    def test_checks_dict_has_all_categories(self):
        result = evaluate_script_quality("Test text.")
        expected_checks = {
            "phrase_violations", "ai_vocabulary", "structural_patterns",
            "rhythm", "conversion_structure", "em_dash", "rule_of_three",
            "contractions", "claims_without_sources",
        }
        self.assertTrue(expected_checks.issubset(result["checks"].keys()))

    def test_severity_weights(self):
        # A script with known HIGH violations should score >= 3 per violation
        text = "Without further ado, let's dive in."
        result = evaluate_script_quality(text)
        if result["high_count"] > 0:
            self.assertGreaterEqual(result["score"], 3.0)

    def test_deduplication(self):
        # Same violation appearing twice should show as one unique rule
        text = "Without further ado, start.\nWithout further ado, again."
        result = evaluate_script_quality(text, max_violations=10)
        phrase_rules = [r for r in result["unique_rules"] if "further ado" in r.lower()]
        self.assertLessEqual(len(phrase_rules), 1)


# ---------------------------------------------------------------------------
# write_quality_report
# ---------------------------------------------------------------------------

class TestWriteQualityReport(unittest.TestCase):
    def test_pass_report(self):
        result = {
            "pass": True, "score": 1.0, "max_violations": 3,
            "high_count": 0, "medium_count": 1, "low_count": 0,
            "total_violations": 1, "unique_rules": ["test"],
            "checks": {"test": 1}, "violations": [],
        }
        report = write_quality_report(result)
        self.assertIn("PASS", report)
        self.assertNotIn("BLOCKER", report)

    def test_fail_report(self):
        result = {
            "pass": False, "score": 10.0, "max_violations": 3,
            "high_count": 5, "medium_count": 2, "low_count": 1,
            "total_violations": 8, "unique_rules": ["r1", "r2"],
            "checks": {"test": 8},
            "violations": [
                {"check": "test", "severity": "HIGH", "rule": "r1",
                 "excerpt": "bad text", "line": 5},
            ],
        }
        report = write_quality_report(result)
        self.assertIn("FAIL", report)
        self.assertIn("BLOCKER", report)

    def test_includes_script_path(self):
        result = {
            "pass": True, "score": 0, "max_violations": 3,
            "high_count": 0, "medium_count": 0, "low_count": 0,
            "total_violations": 0, "unique_rules": [],
            "checks": {}, "violations": [],
        }
        report = write_quality_report(result, "path/to/script.md")
        self.assertIn("path/to/script.md", report)

    def test_groups_by_check(self):
        result = {
            "pass": False, "score": 6.0, "max_violations": 3,
            "high_count": 2, "medium_count": 0, "low_count": 0,
            "total_violations": 2, "unique_rules": ["r1", "r2"],
            "checks": {"phrase_violations": 1, "structural_patterns": 1},
            "violations": [
                {"check": "phrase_violations", "severity": "HIGH",
                 "rule": "r1", "excerpt": "text1", "line": 1},
                {"check": "structural_patterns", "severity": "HIGH",
                 "rule": "r2", "excerpt": "text2", "line": 2},
            ],
        }
        report = write_quality_report(result)
        self.assertIn("Phrase Violations", report)
        self.assertIn("Structural Patterns", report)


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------

class TestConstants(unittest.TestCase):
    def test_banned_phrases_not_empty(self):
        self.assertGreater(len(DEFAULT_BANNED_PHRASES), 10)

    def test_ai_vocabulary_not_empty(self):
        self.assertGreater(len(AI_VOCABULARY), 5)

    def test_short_punch_max_words(self):
        self.assertEqual(SHORT_PUNCH_MAX_WORDS, 4)


if __name__ == "__main__":
    unittest.main()
