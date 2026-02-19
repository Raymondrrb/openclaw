#!/usr/bin/env python3
"""Tests for variation_quality_checks.py — variation scoring, n-gram similarity, disclosure checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Ensure tools/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from variation_quality_checks import (
    _extract_narration_text,
    _ngram_similarity,
    _ngrams,
    check_disclosure_presence,
    check_ngram_similarity,
    check_structure_adherence,
    check_unique_segment_types,
    check_variation_score,
    evaluate_variation_quality,
)


# ---------------------------------------------------------------------------
# check_variation_score
# ---------------------------------------------------------------------------

class TestCheckVariationScore(unittest.TestCase):
    def test_high_score_passes(self):
        plan = {"variation_score": 0.85}
        self.assertEqual(check_variation_score(plan), [])

    def test_low_score_fails(self):
        plan = {"variation_score": 0.3}
        violations = check_variation_score(plan)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["type"], "low_variation_score")
        self.assertEqual(violations[0]["severity"], "HIGH")

    def test_custom_threshold(self):
        plan = {"variation_score": 0.5}
        self.assertEqual(check_variation_score(plan, min_score=0.4), [])
        self.assertEqual(len(check_variation_score(plan, min_score=0.6)), 1)

    def test_missing_score_defaults_to_zero(self):
        plan = {}
        violations = check_variation_score(plan)
        self.assertEqual(len(violations), 1)

    def test_exact_threshold_passes(self):
        plan = {"variation_score": 0.6}
        self.assertEqual(check_variation_score(plan, min_score=0.6), [])


# ---------------------------------------------------------------------------
# check_unique_segment_types
# ---------------------------------------------------------------------------

class TestCheckUniqueSegmentTypes(unittest.TestCase):
    def test_enough_types_passes(self):
        script = {"segments": [{"type": t} for t in
                                ["hook", "intro", "product_review", "comparison",
                                 "recap", "cta", "outro"]]}
        self.assertEqual(check_unique_segment_types(script), [])

    def test_too_few_types_fails(self):
        script = {"segments": [{"type": "review"}, {"type": "review"}]}
        violations = check_unique_segment_types(script)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["type"], "low_segment_variety")

    def test_counts_nested_kinds(self):
        script = {"segments": [
            {"type": "product_block", "segments": [
                {"kind": "hero_shot"},
                {"kind": "use_case"},
                {"kind": "comparison"},
            ]},
            {"type": "intro"},
            {"type": "hook"},
            {"type": "cta"},
            {"type": "outro"},
        ]}
        violations = check_unique_segment_types(script, min_types=6)
        # Should find: product_block, hero_shot, use_case, comparison, intro, hook, cta, outro = 8
        self.assertEqual(violations, [])

    def test_empty_segments(self):
        script = {"segments": []}
        violations = check_unique_segment_types(script)
        self.assertEqual(len(violations), 1)

    def test_custom_min_types(self):
        script = {"segments": [{"type": "a"}, {"type": "b"}, {"type": "c"}]}
        self.assertEqual(check_unique_segment_types(script, min_types=3), [])
        self.assertEqual(len(check_unique_segment_types(script, min_types=4)), 1)


# ---------------------------------------------------------------------------
# _ngrams / _ngram_similarity / _extract_narration_text
# ---------------------------------------------------------------------------

class TestNgrams(unittest.TestCase):
    def test_basic(self):
        result = _ngrams("hello world how are you", 3)
        self.assertEqual(result, ["hello world how", "world how are", "how are you"])

    def test_short_text(self):
        result = _ngrams("hi there", 3)
        self.assertEqual(result, [])

    def test_strips_non_alpha(self):
        result = _ngrams("Hello, World! 123", 2)
        self.assertEqual(result, ["hello world"])


class TestNgramSimilarity(unittest.TestCase):
    def test_identical_texts(self):
        text = "the quick brown fox jumps over the lazy dog"
        sim = _ngram_similarity(text, text)
        self.assertAlmostEqual(sim, 1.0)

    def test_completely_different(self):
        text_a = "alpha beta gamma delta epsilon"
        text_b = "one two three four five six seven"
        sim = _ngram_similarity(text_a, text_b)
        self.assertAlmostEqual(sim, 0.0)

    def test_partial_overlap(self):
        text_a = "the quick brown fox jumps over the lazy dog"
        text_b = "the quick brown cat sits on the lazy couch"
        sim = _ngram_similarity(text_a, text_b)
        self.assertGreater(sim, 0.0)
        self.assertLess(sim, 1.0)

    def test_empty_text(self):
        self.assertEqual(_ngram_similarity("", "hello world test"), 0.0)


class TestExtractNarrationText(unittest.TestCase):
    def test_narration_field(self):
        script = {"segments": [{"narration": "Hello there"}]}
        self.assertIn("Hello there", _extract_narration_text(script))

    def test_voice_text_field(self):
        script = {"segments": [{"voice_text": "Voice here"}]}
        self.assertIn("Voice here", _extract_narration_text(script))

    def test_nested_segments(self):
        script = {"segments": [{"segments": [{"narration": "Nested text"}]}]}
        self.assertIn("Nested text", _extract_narration_text(script))

    def test_structure_key(self):
        script = {"segments": [], "structure": [{"voice_text": "Struct text"}]}
        self.assertIn("Struct text", _extract_narration_text(script))

    def test_empty_script(self):
        self.assertEqual(_extract_narration_text({}), "")


# ---------------------------------------------------------------------------
# check_ngram_similarity
# ---------------------------------------------------------------------------

class TestCheckNgramSimilarity(unittest.TestCase):
    def test_no_recent_scripts(self):
        self.assertEqual(check_ngram_similarity("hello world", []), [])

    def test_high_similarity_flagged(self):
        text = "the quick brown fox jumps over the lazy dog again and again"
        recent = [{"segments": [{"narration": text}], "run_id": "old_run"}]
        violations = check_ngram_similarity(text, recent, max_sim=0.3)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["type"], "high_ngram_similarity")
        self.assertIn("old_run", violations[0]["rule"])

    def test_low_similarity_passes(self):
        text = "alpha beta gamma delta epsilon zeta eta theta"
        recent = [{"segments": [{"narration": "one two three four five six seven eight"}]}]
        violations = check_ngram_similarity(text, recent, max_sim=0.4)
        self.assertEqual(violations, [])


# ---------------------------------------------------------------------------
# check_disclosure_presence
# ---------------------------------------------------------------------------

class TestCheckDisclosurePresence(unittest.TestCase):
    def test_no_disclosure_required(self):
        script = {"segments": []}
        plan = {"prompt_instructions": {}}
        self.assertEqual(check_disclosure_presence(script, plan), [])

    def test_both_disclosures_present(self):
        script = {"segments": [
            {"narration": "We use affiliate links. This video was AI assisted with tools."}
        ]}
        plan = {"prompt_instructions": {"disclosure_text": "affiliate + AI"}}
        violations = check_disclosure_presence(script, plan)
        self.assertEqual(violations, [])

    def test_missing_affiliate_disclosure(self):
        script = {"segments": [
            {"narration": "This video was AI assisted with tools."}
        ]}
        plan = {"prompt_instructions": {"disclosure_text": "both"}}
        violations = check_disclosure_presence(script, plan)
        types = [v["type"] for v in violations]
        self.assertIn("missing_affiliate_disclosure", types)

    def test_missing_ai_disclosure(self):
        script = {"segments": [
            {"narration": "We use affiliate links."}
        ]}
        plan = {"prompt_instructions": {"disclosure_text": "both"}}
        violations = check_disclosure_presence(script, plan)
        types = [v["type"] for v in violations]
        self.assertIn("missing_ai_disclosure", types)

    def test_severity_levels(self):
        script = {"segments": [{"narration": "Nothing relevant here."}]}
        plan = {"prompt_instructions": {"disclosure_text": "required"}}
        violations = check_disclosure_presence(script, plan)
        aff = [v for v in violations if v["type"] == "missing_affiliate_disclosure"]
        ai = [v for v in violations if v["type"] == "missing_ai_disclosure"]
        self.assertEqual(aff[0]["severity"], "HIGH")
        self.assertEqual(ai[0]["severity"], "MEDIUM")


# ---------------------------------------------------------------------------
# check_structure_adherence
# ---------------------------------------------------------------------------

class TestCheckStructureAdherence(unittest.TestCase):
    def test_matching_structure(self):
        script = {"segments": [
            {"type": "hook"}, {"type": "intro"}, {"type": "product_review"},
        ]}
        plan = {
            "selections": {"structure_template": "classic_countdown"},
            "prompt_instructions": {"segments_per_product": ["hook", "intro"]},
        }
        violations = check_structure_adherence(script, plan)
        self.assertEqual(violations, [])

    def test_missing_segment_type(self):
        script = {"segments": [{"type": "hook"}, {"type": "outro"}]}
        plan = {
            "selections": {"structure_template": "problem_solution"},
            "prompt_instructions": {"segments_per_product": ["hook", "intro", "comparison"]},
        }
        violations = check_structure_adherence(script, plan)
        types_missing = [v["rule"] for v in violations]
        self.assertTrue(any("intro" in r for r in types_missing))
        self.assertTrue(any("comparison" in r for r in types_missing))

    def test_no_expected_segments(self):
        script = {"segments": [{"type": "hook"}]}
        plan = {"selections": {}, "prompt_instructions": {}}
        self.assertEqual(check_structure_adherence(script, plan), [])


# ---------------------------------------------------------------------------
# evaluate_variation_quality (integration)
# ---------------------------------------------------------------------------

class TestEvaluateVariationQuality(unittest.TestCase):
    def test_good_variation_passes(self):
        script = {"segments": [
            {"type": t, "narration": f"This is unique narration for {t} about affiliate links and AI tools assistance."}
            for t in ["hook", "intro", "product_review", "comparison", "recap", "cta", "disclosure"]
        ]}
        plan = {
            "variation_score": 0.85,
            "selections": {"structure_template": "classic_countdown"},
            "prompt_instructions": {"disclosure_text": "affiliate + AI", "segments_per_product": ["hook"]},
            "constraints": {"min_variation_score": 0.6},
        }
        violations = evaluate_variation_quality(script, plan)
        high_violations = [v for v in violations if v["severity"] == "HIGH"]
        self.assertEqual(high_violations, [])

    def test_all_violations_tagged(self):
        violations = evaluate_variation_quality({"segments": []}, {"variation_score": 0.1})
        for v in violations:
            self.assertEqual(v["check"], "variation_quality")

    def test_uses_plan_min_score(self):
        plan = {
            "variation_score": 0.55,
            "constraints": {"min_variation_score": 0.5},
        }
        violations = evaluate_variation_quality({"segments": []}, plan)
        score_violations = [v for v in violations if v["type"] == "low_variation_score"]
        self.assertEqual(score_violations, [])  # 0.55 >= 0.5, passes

    def test_recent_scripts_similarity(self):
        narration = "the quick brown fox jumps over the lazy dog again repeated"
        script = {"segments": [{"narration": narration}]}
        recent = [{"segments": [{"narration": narration}], "run_id": "prev_run"}]
        plan = {"variation_score": 0.9}
        violations = evaluate_variation_quality(script, plan, recent)
        sim_violations = [v for v in violations if v["type"] == "high_ngram_similarity"]
        self.assertGreater(len(sim_violations), 0)


if __name__ == "__main__":
    unittest.main()
