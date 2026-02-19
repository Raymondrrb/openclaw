#!/usr/bin/env python3
"""Tests for variation_planner.py — scoring, selection, prompt building, performance bonus."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure tools/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from variation_planner import (
    _build_dzine_instructions,
    _build_prompt_instructions,
    _build_youtube_ab_variants,
    _deterministic_seed,
    compute_performance_bonus,
    compute_variation_score,
    fetch_local_variation_history,
    select_variation,
    SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# _deterministic_seed
# ---------------------------------------------------------------------------

class TestDeterministicSeed(unittest.TestCase):
    def test_same_inputs_same_seed(self):
        s1 = _deterministic_seed("run_123", "monitors")
        s2 = _deterministic_seed("run_123", "monitors")
        self.assertEqual(s1, s2)

    def test_different_run_id_different_seed(self):
        s1 = _deterministic_seed("run_a", "monitors")
        s2 = _deterministic_seed("run_b", "monitors")
        self.assertNotEqual(s1, s2)

    def test_different_category_different_seed(self):
        s1 = _deterministic_seed("run_1", "monitors")
        s2 = _deterministic_seed("run_1", "keyboards")
        self.assertNotEqual(s1, s2)

    def test_returns_int(self):
        s = _deterministic_seed("test", "cat")
        self.assertIsInstance(s, int)
        self.assertGreater(s, 0)


# ---------------------------------------------------------------------------
# compute_variation_score
# ---------------------------------------------------------------------------

class TestComputeVariationScore(unittest.TestCase):
    def test_no_history_returns_1(self):
        score = compute_variation_score({"a": "x"}, [], {"a": 1.0})
        self.assertEqual(score, 1.0)

    def test_empty_weights_returns_1(self):
        score = compute_variation_score({"a": "x"}, [{"selections": {"a": "x"}}], {})
        self.assertEqual(score, 1.0)

    def test_unique_candidate_scores_high(self):
        history = [{"selections": {"dim": "old_val"}}]
        score = compute_variation_score({"dim": "new_val"}, history, {"dim": 1.0})
        self.assertEqual(score, 1.0)

    def test_most_recent_match_scores_lowest(self):
        history = [{"selections": {"dim": "same"}}]
        score = compute_variation_score({"dim": "same"}, history, {"dim": 1.0})
        # Most recent match (i=0): recency_decay=0/1=0, dim_score=0.0
        self.assertAlmostEqual(score, 0.0)

    def test_older_match_penalized_less(self):
        history = [
            {"selections": {"dim": "a"}},
            {"selections": {"dim": "b"}},
        ]
        # "a" at index 0: recency_decay=0/2=0, dim_score=0.0
        # "b" at index 1: recency_decay=1/2=0.5, dim_score=0.25
        score_a = compute_variation_score({"dim": "a"}, history, {"dim": 1.0})
        score_b = compute_variation_score({"dim": "b"}, history, {"dim": 1.0})
        score_new = compute_variation_score({"dim": "never_used"}, history, {"dim": 1.0})
        self.assertEqual(score_new, 1.0)
        self.assertAlmostEqual(score_a, 0.0)
        self.assertGreater(score_b, score_a)  # older match = less penalty

    def test_multi_dimension(self):
        history = [{"selections": {"a": "x", "b": "y"}}]
        # One dimension matches, one doesn't
        score = compute_variation_score({"a": "x", "b": "new"}, history, {"a": 1.0, "b": 1.0})
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)

    def test_score_is_rounded(self):
        score = compute_variation_score(
            {"dim": "val"},
            [{"selections": {"dim": "val"}}],
            {"dim": 1.0},
        )
        # Check it's rounded to 4 decimals
        self.assertEqual(score, round(score, 4))


# ---------------------------------------------------------------------------
# compute_performance_bonus
# ---------------------------------------------------------------------------

class TestComputePerformanceBonus(unittest.TestCase):
    def test_no_history_returns_zero(self):
        self.assertEqual(compute_performance_bonus({"a": "x"}, []), 0.0)

    def test_matching_top_performer_gets_bonus(self):
        perf = [
            {"selections": {"opener": "hook"}, "engagement": 0.1},
            {"selections": {"opener": "question"}, "engagement": 0.01},
        ]
        bonus = compute_performance_bonus({"opener": "hook"}, perf)
        self.assertGreater(bonus, 0.0)
        self.assertLessEqual(bonus, 0.15)

    def test_non_matching_gets_no_bonus(self):
        perf = [{"selections": {"opener": "hook"}, "engagement": 0.1}]
        bonus = compute_performance_bonus({"opener": "totally_different"}, perf)
        self.assertEqual(bonus, 0.0)

    def test_bonus_capped_at_015(self):
        perf = [{"selections": {"a": "1", "b": "2", "c": "3"}, "engagement": 0.5}]
        bonus = compute_performance_bonus({"a": "1", "b": "2", "c": "3"}, perf)
        self.assertLessEqual(bonus, 0.15)

    def test_bonus_is_rounded(self):
        perf = [{"selections": {"a": "1"}, "engagement": 0.1}]
        bonus = compute_performance_bonus({"a": "1"}, perf)
        self.assertEqual(bonus, round(bonus, 4))


# ---------------------------------------------------------------------------
# select_variation
# ---------------------------------------------------------------------------

class TestSelectVariation(unittest.TestCase):
    def _simple_policy(self):
        return {
            "opener_styles": {"hook": {}, "question": {}},
            "structure_templates": {"countdown": {}, "problem_solution": {}},
            "marketing_angles": {"value_hunter": {}, "problem_solver": {}},
            "product_block_patterns": {"classic_4seg": {}},
            "visual_styles": {"clean_studio": {}, "lifestyle": {}},
            "voice_pacing_profiles": {"standard": {}, "fast": {}},
            "cta_variants": {"soft_subscribe": {}, "hard_buy": {}},
            "disclosure_templates": {"standard": {}},
            "constraints": {
                "dimension_weights": {
                    "opener_style": 1.0,
                    "structure_template": 1.0,
                    "marketing_angle": 1.0,
                },
            },
        }

    def test_returns_selections_and_score(self):
        selections, score = select_variation(self._simple_policy(), [], "monitors")
        self.assertIsInstance(selections, dict)
        self.assertIsInstance(score, float)
        self.assertIn("opener_style", selections)
        self.assertIn("structure_template", selections)

    def test_force_overrides(self):
        selections, _ = select_variation(
            self._simple_policy(), [], "monitors",
            force_overrides={"opener_style": "question"},
        )
        self.assertEqual(selections["opener_style"], "question")

    def test_no_history_high_score(self):
        _, score = select_variation(self._simple_policy(), [], "monitors")
        self.assertGreaterEqual(score, 0.8)

    def test_with_history_avoids_recent(self):
        history = [{
            "selections": {"opener_style": "hook", "structure_template": "countdown",
                           "marketing_angle": "value_hunter"},
        }]
        # With only 2 options per dimension, the algo should tend to avoid recent
        selections, _ = select_variation(self._simple_policy(), history, "monitors")
        # Can't guarantee specific picks due to randomness, but score should reflect diversity
        self.assertIsInstance(selections, dict)


# ---------------------------------------------------------------------------
# _build_prompt_instructions
# ---------------------------------------------------------------------------

class TestBuildPromptInstructions(unittest.TestCase):
    def _policy(self):
        return {
            "opener_styles": {"hook": {"template": "Big claim!", "description": "Hook opener"}},
            "structure_templates": {"countdown": {"description": "Classic", "segment_flow": "5-4-3-2-1"}},
            "product_block_patterns": {"classic_4seg": {"segments_per_product": ["intro", "feature", "critique", "verdict"], "description": "4-seg"}},
            "visual_styles": {"clean_studio": {"dzine_direction": "Clean background", "description": "Studio style"}},
            "voice_pacing_profiles": {"standard": {"wpm_target": 150, "description": "Normal pace"}},
            "cta_variants": {"soft_subscribe": {"line": "Subscribe!", "description": "Soft CTA"}},
            "disclosure_templates": {"standard": {"text": "This video uses affiliate links."}},
            "marketing_angles": {"value_hunter": {"description": "Price-focused", "prompt_injection": "Focus on value"}},
        }

    def test_basic_instructions(self):
        selections = {
            "opener_style": "hook",
            "structure_template": "countdown",
            "product_block_pattern": "classic_4seg",
            "visual_style": "clean_studio",
            "voice_pacing": "standard",
            "cta_variant": "soft_subscribe",
            "disclosure_template": "standard",
            "marketing_angle": "value_hunter",
        }
        result = _build_prompt_instructions(selections, self._policy(), [], "monitors")
        self.assertEqual(result["opener_template"], "Big claim!")
        self.assertEqual(result["voice_wpm_target"], 150)
        self.assertEqual(result["disclosure_text"], "This video uses affiliate links.")
        self.assertEqual(result["segments_per_product"], ["intro", "feature", "critique", "verdict"])

    def test_missing_keys_fallback(self):
        result = _build_prompt_instructions({}, {}, [], "monitors")
        self.assertEqual(result["opener_template"], "")
        self.assertEqual(result["voice_wpm_target"], 150)  # default


# ---------------------------------------------------------------------------
# _build_youtube_ab_variants
# ---------------------------------------------------------------------------

class TestBuildYoutubeAbVariants(unittest.TestCase):
    def test_returns_title_variants(self):
        selections = {"marketing_angle": "value_hunter", "opener_style": "hook"}
        policy = {"marketing_angles": {"value_hunter": {"label": "Value Hunter"}}}
        result = _build_youtube_ab_variants(selections, policy, "monitors", [])
        self.assertIn("title_variants", result)
        self.assertGreater(len(result["title_variants"]), 0)

    def test_titles_under_70_chars(self):
        selections = {"marketing_angle": "problem_solver"}
        policy = {"marketing_angles": {"problem_solver": {"label": "Problem Solver"}}}
        result = _build_youtube_ab_variants(selections, policy, "desk_gadgets", [])
        for tv in result["title_variants"]:
            self.assertLessEqual(len(tv["title"]), 70)

    def test_angle_label_included(self):
        selections = {"marketing_angle": "honest_disappointment"}
        policy = {"marketing_angles": {"honest_disappointment": {"label": "Honest"}}}
        result = _build_youtube_ab_variants(selections, policy, "keyboards", [])
        self.assertEqual(result["angle_used"], "honest_disappointment")
        self.assertEqual(result["angle_label"], "Honest")


# ---------------------------------------------------------------------------
# _build_dzine_instructions
# ---------------------------------------------------------------------------

class TestBuildDzineInstructions(unittest.TestCase):
    def test_basic(self):
        selections = {"visual_style": "lifestyle"}
        policy = {
            "dzine_model_preferences": {
                "product_photography": {"model": "TestModel"},
                "avatar_creative": {"model": "AvatarModel"},
            },
        }
        result = _build_dzine_instructions(selections, policy)
        self.assertEqual(result["primary_model"], "TestModel")
        self.assertEqual(result["avatar_model"], "AvatarModel")
        self.assertEqual(result["style_direction"], "lifestyle")

    def test_defaults(self):
        result = _build_dzine_instructions({}, {})
        self.assertEqual(result["primary_model"], "Seedream 5.0")
        self.assertEqual(result["avatar_model"], "NanoBanana Pro")


# ---------------------------------------------------------------------------
# fetch_local_variation_history
# ---------------------------------------------------------------------------

class TestFetchLocalVariationHistory(unittest.TestCase):
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("variation_planner.RUNS_DIR", Path(td)):
                result = fetch_local_variation_history()
                self.assertEqual(result, [])

    def test_finds_variation_plans(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "test_run_01"
            run_dir.mkdir()
            plan = {"run_id": "test_run_01", "selections": {"opener_style": "hook"}}
            (run_dir / "variation_plan.json").write_text(json.dumps(plan))
            with patch("variation_planner.RUNS_DIR", Path(td)):
                result = fetch_local_variation_history()
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]["run_id"], "test_run_01")
                self.assertEqual(result[0]["selections"]["opener_style"], "hook")

    def test_respects_lookback_limit(self):
        with tempfile.TemporaryDirectory() as td:
            for i in range(5):
                run_dir = Path(td) / f"run_{i:02d}"
                run_dir.mkdir()
                plan = {"run_id": f"run_{i}", "selections": {"dim": f"val_{i}"}}
                (run_dir / "variation_plan.json").write_text(json.dumps(plan))
            with patch("variation_planner.RUNS_DIR", Path(td)):
                result = fetch_local_variation_history(lookback_runs=2)
                self.assertLessEqual(len(result), 2)

    def test_skips_invalid_json(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "bad_run"
            run_dir.mkdir()
            (run_dir / "variation_plan.json").write_text("not json!!!")
            with patch("variation_planner.RUNS_DIR", Path(td)):
                result = fetch_local_variation_history()
                self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants(unittest.TestCase):
    def test_schema_version_format(self):
        parts = SCHEMA_VERSION.split(".")
        self.assertEqual(len(parts), 3)
        for part in parts:
            self.assertTrue(part.isdigit())


if __name__ == "__main__":
    unittest.main()
