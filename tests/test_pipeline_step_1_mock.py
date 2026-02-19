#!/usr/bin/env python3
"""Tests for tools/pipeline_step_1_generate_script.py — generate_mock."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from pipeline_step_1_generate_script import generate_mock
from video_pipeline_lib import Product


def _make_product(title="Test Product", price=29.99, rating=4.5, reviews=100, score=0.8):
    return Product(
        product_title=title,
        asin="B000TEST",
        current_price_usd=price,
        rating=rating,
        review_count=reviews,
        feature_bullets=["Feature 1", "Feature 2"],
        amazon_url="https://amazon.com/dp/B000TEST",
        affiliate_url="https://amazon.com/dp/B000TEST?tag=test-20",
        ranking_score=score,
    )


# ---------------------------------------------------------------
# generate_mock
# ---------------------------------------------------------------

class TestGenerateMock(unittest.TestCase):

    def test_returns_dict(self):
        products = [_make_product()]
        result = generate_mock(products, "earbuds", "Rayviews")
        self.assertIsInstance(result, dict)

    def test_has_video_title(self):
        result = generate_mock([_make_product()], "earbuds", "Rayviews")
        self.assertIn("earbuds", result["video_title"])

    def test_has_segments(self):
        result = generate_mock([_make_product()], "speakers", "Rayviews")
        self.assertIsInstance(result["segments"], list)
        self.assertGreater(len(result["segments"]), 0)

    def test_word_count_positive(self):
        result = generate_mock([_make_product()], "monitors", "Rayviews")
        self.assertGreater(result["total_word_count"], 0)

    def test_estimated_duration_positive(self):
        result = generate_mock([_make_product()], "monitors", "Rayviews")
        self.assertGreater(result["estimated_duration_minutes"], 0)

    def test_word_count_matches_segments(self):
        result = generate_mock([_make_product()], "mice", "Rayviews")
        actual = sum(len(s.get("narration", "").split()) for s in result["segments"])
        self.assertEqual(result["total_word_count"], actual)

    def test_has_youtube_metadata(self):
        result = generate_mock([_make_product()], "keyboards", "Rayviews")
        yt = result["youtube"]
        self.assertIn("description", yt)
        self.assertIn("tags", yt)
        self.assertIn("chapters", yt)

    def test_hook_segment_first(self):
        result = generate_mock([_make_product()], "webcams", "Rayviews")
        self.assertEqual(result["segments"][0]["type"], "HOOK")

    def test_ending_segment_last(self):
        result = generate_mock([_make_product()], "webcams", "Rayviews")
        self.assertEqual(result["segments"][-1]["type"], "ENDING_DECISION")

    def test_credibility_after_hook(self):
        result = generate_mock([_make_product()], "headsets", "Rayviews")
        self.assertEqual(result["segments"][1]["type"], "CREDIBILITY")

    def test_criteria_segment_exists(self):
        result = generate_mock([_make_product()], "headphones", "Rayviews")
        types = [s["type"] for s in result["segments"]]
        self.assertIn("CRITERIA", types)

    def test_product_segments_for_each_product(self):
        products = [
            _make_product("Alpha", score=0.9),
            _make_product("Beta", score=0.7),
            _make_product("Gamma", score=0.5),
        ]
        result = generate_mock(products, "speakers", "Rayviews")
        product_intros = [s for s in result["segments"] if s["type"] == "PRODUCT_INTRO"]
        self.assertEqual(len(product_intros), 3)

    def test_products_ranked_by_score(self):
        products = [
            _make_product("Low", score=0.3),
            _make_product("High", score=0.9),
            _make_product("Mid", score=0.6),
        ]
        result = generate_mock(products, "cameras", "Rayviews")
        intros = [s for s in result["segments"] if s["type"] == "PRODUCT_INTRO"]
        # Reversed sorted → #5 is lowest, #1 is highest
        names = [s["product_name"] for s in intros]
        self.assertEqual(names[0], "Low")   # worst ranked = shown first (as #5)
        self.assertEqual(names[-1], "High") # best ranked = shown last (as #1)

    def test_winner_reinforcement_mentions_top_product(self):
        products = [
            _make_product("Best Product", score=0.99),
            _make_product("Other", score=0.1),
        ]
        result = generate_mock(products, "monitors", "Rayviews")
        winner = [s for s in result["segments"] if s["type"] == "WINNER_REINFORCEMENT"]
        self.assertEqual(len(winner), 1)
        self.assertIn("Best Product", winner[0]["narration"])

    def test_forward_hooks_between_products(self):
        products = [
            _make_product("A", score=0.9),
            _make_product("B", score=0.5),
        ]
        result = generate_mock(products, "phones", "Rayviews")
        types = [s["type"] for s in result["segments"]]
        self.assertIn("FORWARD_HOOK", types)

    def test_disclosure_in_ending(self):
        result = generate_mock([_make_product()], "tablets", "Rayviews")
        ending = result["segments"][-1]
        self.assertIn("affiliate", ending["narration"].lower())
        self.assertIn("AI", ending["narration"])

    def test_five_products_full(self):
        products = [_make_product(f"P{i}", score=i * 0.2) for i in range(5)]
        result = generate_mock(products, "earbuds", "Rayviews")
        intros = [s for s in result["segments"] if s["type"] == "PRODUCT_INTRO"]
        self.assertEqual(len(intros), 5)

    def test_deterministic_output(self):
        products = [_make_product("X", score=0.5)]
        r1 = generate_mock(products, "earbuds", "Rayviews")
        r2 = generate_mock(products, "earbuds", "Rayviews")
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
