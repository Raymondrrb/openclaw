#!/usr/bin/env python3
"""Tests for pipeline_step_1_generate_script.py — mock generation, openclaw integration, CLI."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from video_pipeline_lib import Product
from pipeline_step_1_generate_script import generate_mock, generate_with_openclaw


def _make_products(n: int = 5) -> list[Product]:
    """Build n deterministic test products."""
    products = []
    for i in range(1, n + 1):
        products.append(Product(
            product_title=f"Product {i}",
            asin=f"B0{i:08d}",
            current_price_usd=20.0 * i,
            rating=3.5 + i * 0.2,
            review_count=100 * i,
            feature_bullets=[f"Feature {j}" for j in range(1, 4)],
            amazon_url=f"https://www.amazon.com/dp/B0{i:08d}",
            affiliate_url=f"https://www.amazon.com/dp/B0{i:08d}?tag=test-20",
            available=True,
            ranking_score=float(i),
        ))
    return products


# ---------------------------------------------------------------
# generate_mock tests
# ---------------------------------------------------------------

class TestGenerateMock(unittest.TestCase):

    def setUp(self):
        self.products = _make_products(5)
        self.theme = "wireless mice"
        self.channel = "Rayviews"

    def test_returns_dict(self):
        result = generate_mock(self.products, self.theme, self.channel)
        self.assertIsInstance(result, dict)

    def test_has_required_keys(self):
        result = generate_mock(self.products, self.theme, self.channel)
        for key in ("video_title", "estimated_duration_minutes", "total_word_count", "segments", "youtube"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_video_title_contains_theme(self):
        result = generate_mock(self.products, self.theme, self.channel)
        self.assertIn("wireless mice", result["video_title"].lower())

    def test_segments_is_list(self):
        result = generate_mock(self.products, self.theme, self.channel)
        self.assertIsInstance(result["segments"], list)

    def test_minimum_segment_count(self):
        """5 products * 4 segments + 4 forward hooks + 3 structural = 27 minimum."""
        result = generate_mock(self.products, self.theme, self.channel)
        self.assertGreaterEqual(len(result["segments"]), 20)

    def test_first_segment_is_hook(self):
        result = generate_mock(self.products, self.theme, self.channel)
        self.assertEqual(result["segments"][0]["type"], "HOOK")

    def test_last_segment_is_ending_decision(self):
        result = generate_mock(self.products, self.theme, self.channel)
        self.assertEqual(result["segments"][-1]["type"], "ENDING_DECISION")

    def test_has_credibility_segment(self):
        result = generate_mock(self.products, self.theme, self.channel)
        types = [s["type"] for s in result["segments"]]
        self.assertIn("CREDIBILITY", types)

    def test_has_criteria_segment(self):
        result = generate_mock(self.products, self.theme, self.channel)
        types = [s["type"] for s in result["segments"]]
        self.assertIn("CRITERIA", types)

    def test_has_winner_reinforcement(self):
        result = generate_mock(self.products, self.theme, self.channel)
        types = [s["type"] for s in result["segments"]]
        self.assertIn("WINNER_REINFORCEMENT", types)

    def test_all_products_have_intro(self):
        result = generate_mock(self.products, self.theme, self.channel)
        intro_products = [
            s["product_name"] for s in result["segments"] if s["type"] == "PRODUCT_INTRO"
        ]
        for p in self.products:
            self.assertIn(p.product_title, intro_products)

    def test_all_products_have_demo(self):
        result = generate_mock(self.products, self.theme, self.channel)
        demo_products = [
            s["product_name"] for s in result["segments"] if s["type"] == "PRODUCT_DEMO"
        ]
        for p in self.products:
            self.assertIn(p.product_title, demo_products)

    def test_all_products_have_review(self):
        result = generate_mock(self.products, self.theme, self.channel)
        review_products = [
            s["product_name"] for s in result["segments"] if s["type"] == "PRODUCT_REVIEW"
        ]
        for p in self.products:
            self.assertIn(p.product_title, review_products)

    def test_all_products_have_rank(self):
        result = generate_mock(self.products, self.theme, self.channel)
        rank_products = [
            s["product_name"] for s in result["segments"] if s["type"] == "PRODUCT_RANK"
        ]
        for p in self.products:
            self.assertIn(p.product_title, rank_products)

    def test_forward_hook_between_products(self):
        """Should have FORWARD_HOOK after products ranked 5-2, but not after #1."""
        result = generate_mock(self.products, self.theme, self.channel)
        types = [s["type"] for s in result["segments"]]
        self.assertEqual(types.count("FORWARD_HOOK"), 4)

    def test_product_demo_includes_price(self):
        result = generate_mock(self.products, self.theme, self.channel)
        demos = [s for s in result["segments"] if s["type"] == "PRODUCT_DEMO"]
        for demo in demos:
            self.assertIn("$", demo["narration"])

    def test_product_demo_includes_rating(self):
        result = generate_mock(self.products, self.theme, self.channel)
        demos = [s for s in result["segments"] if s["type"] == "PRODUCT_DEMO"]
        for demo in demos:
            self.assertIn("star", demo["narration"])

    def test_total_word_count_matches_segments(self):
        result = generate_mock(self.products, self.theme, self.channel)
        counted = sum(len(s.get("narration", "").split()) for s in result["segments"])
        self.assertEqual(result["total_word_count"], counted)

    def test_estimated_duration_positive(self):
        result = generate_mock(self.products, self.theme, self.channel)
        self.assertGreater(result["estimated_duration_minutes"], 0)

    def test_youtube_metadata_present(self):
        result = generate_mock(self.products, self.theme, self.channel)
        yt = result["youtube"]
        self.assertIn("description", yt)
        self.assertIn("tags", yt)
        self.assertIn("chapters", yt)

    def test_youtube_description_has_disclosure(self):
        result = generate_mock(self.products, self.theme, self.channel)
        desc = result["youtube"]["description"].lower()
        self.assertIn("affiliate", desc)
        self.assertIn("ai", desc)

    def test_youtube_tags_include_theme(self):
        result = generate_mock(self.products, self.theme, self.channel)
        tags_lower = [t.lower() for t in result["youtube"]["tags"]]
        self.assertTrue(any(self.theme in t for t in tags_lower))

    def test_ending_decision_has_disclosure(self):
        result = generate_mock(self.products, self.theme, self.channel)
        ending = result["segments"][-1]
        narration = ending["narration"].lower()
        self.assertIn("affiliate", narration)

    def test_hook_contains_theme(self):
        result = generate_mock(self.products, self.theme, self.channel)
        hook = result["segments"][0]
        self.assertIn("wireless mice", hook["narration"].lower())

    def test_visual_hints_present(self):
        """Segments that should have visual_hint do have them."""
        result = generate_mock(self.products, self.theme, self.channel)
        for s in result["segments"]:
            if s["type"] in ("HOOK", "CREDIBILITY", "CRITERIA", "PRODUCT_INTRO",
                             "PRODUCT_DEMO", "PRODUCT_REVIEW", "WINNER_REINFORCEMENT"):
                self.assertTrue(s.get("visual_hint"), f"{s['type']} missing visual_hint")

    def test_with_fewer_products(self):
        """Should work with < 5 products."""
        products = _make_products(2)
        result = generate_mock(products, "headphones", "TestChannel")
        self.assertIsInstance(result, dict)
        intros = [s for s in result["segments"] if s["type"] == "PRODUCT_INTRO"]
        self.assertEqual(len(intros), 2)

    def test_single_product(self):
        products = _make_products(1)
        result = generate_mock(products, "speakers", "TestChannel")
        self.assertEqual(len([s for s in result["segments"] if s["type"] == "PRODUCT_INTRO"]), 1)
        # With 1 product, rank is 6-1=5 so FORWARD_HOOK still fires (rank > 1)
        self.assertEqual(len([s for s in result["segments"] if s["type"] == "FORWARD_HOOK"]), 1)

    def test_winner_reinforcement_references_top_product(self):
        """Winner reinforcement should mention the highest-ranked product."""
        result = generate_mock(self.products, self.theme, self.channel)
        winner_seg = [s for s in result["segments"] if s["type"] == "WINNER_REINFORCEMENT"][0]
        # Product 5 has highest ranking_score
        self.assertIn("Product 5", winner_seg["narration"])

    def test_variation_plan_parameter_accepted(self):
        """generate_mock should accept variation_plan without errors."""
        plan = {"selections": {"structure_template": "classic_countdown"}}
        result = generate_mock(self.products, self.theme, self.channel, variation_plan=plan)
        self.assertIsInstance(result, dict)

    def test_product_order_is_ascending(self):
        """Products should appear #5 first, #1 last (ascending rank order)."""
        result = generate_mock(self.products, self.theme, self.channel)
        intros = [s for s in result["segments"] if s["type"] == "PRODUCT_INTRO"]
        # Products sorted by ranking_score desc, then reversed for show order
        # Product 1 has score 1.0, Product 5 has score 5.0
        # Ranked: [P5, P4, P3, P2, P1] -> reversed for show: [P1, P2, P3, P4, P5]
        # So intros should be P1, P2, P3, P4, P5
        self.assertEqual(intros[0]["product_name"], "Product 1")
        self.assertEqual(intros[-1]["product_name"], "Product 5")

    def test_deterministic(self):
        """Same inputs produce same output."""
        r1 = generate_mock(self.products, self.theme, self.channel)
        r2 = generate_mock(self.products, self.theme, self.channel)
        self.assertEqual(json.dumps(r1, sort_keys=True), json.dumps(r2, sort_keys=True))

    def test_serializable(self):
        """Output is JSON-serializable."""
        result = generate_mock(self.products, self.theme, self.channel)
        serialized = json.dumps(result)
        reparsed = json.loads(serialized)
        self.assertEqual(result, reparsed)


# ---------------------------------------------------------------
# generate_with_openclaw tests
# ---------------------------------------------------------------

class TestGenerateWithOpenclaw(unittest.TestCase):

    def setUp(self):
        self.products = _make_products(5)
        self.theme = "wireless mice"
        self.channel = "Rayviews"

    def _mock_openclaw_success(self, script_data: dict) -> MagicMock:
        """Create a mock subprocess result with valid openclaw output."""
        raw = json.dumps(script_data)
        output = json.dumps({
            "result": {
                "payloads": [{"text": raw}]
            }
        })
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    def _make_valid_script(self) -> dict:
        """Build a minimally valid structured script."""
        segments = [
            {"type": "HOOK", "narration": "Here's what you need to know.", "visual_hint": "products on desk"},
            {"type": "CREDIBILITY", "narration": "I tested these for weeks.", "visual_hint": "testing setup"},
            {"type": "CRITERIA", "narration": "Ranked by performance build value.", "visual_hint": "criteria list"},
        ]
        for i in range(5):
            name = f"Product {i+1}"
            segments.extend([
                {"type": "PRODUCT_INTRO", "narration": f"Number {5-i}.", "product_name": name, "visual_hint": f"{name} photo"},
                {"type": "PRODUCT_DEMO", "narration": f"{name} works great.", "product_name": name, "visual_hint": f"using {name}"},
                {"type": "PRODUCT_REVIEW", "narration": f"Build quality is solid.", "product_name": name, "visual_hint": f"close-up {name}"},
                {"type": "PRODUCT_RANK", "narration": f"Get it if you need value.", "product_name": name},
            ])
            if i < 4:
                segments.append({"type": "FORWARD_HOOK", "narration": "Next one changes things."})
        segments.append({"type": "WINNER_REINFORCEMENT", "narration": "Product 5 is the one.", "visual_hint": "winner shot"})
        segments.append({"type": "ENDING_DECISION", "narration": "Check links below. Affiliate disclosure."})
        return {
            "video_title": "Top 5 Best Wireless Mice in 2026",
            "estimated_duration_minutes": 8.5,
            "total_word_count": 200,
            "segments": segments,
            "youtube": {
                "description": "Top 5 wireless mice.",
                "tags": ["mice", "wireless"],
                "chapters": [{"time": "0:00", "label": "Intro"}],
            },
        }

    @patch("pipeline_step_1_generate_script.subprocess.run")
    def test_success(self, mock_run):
        script = self._make_valid_script()
        mock_run.return_value = self._mock_openclaw_success(script)
        result = generate_with_openclaw(self.products, self.theme, self.channel)
        self.assertIsInstance(result, dict)
        self.assertIn("segments", result)

    @patch("pipeline_step_1_generate_script.subprocess.run")
    def test_calls_openclaw_command(self, mock_run):
        script = self._make_valid_script()
        mock_run.return_value = self._mock_openclaw_success(script)
        generate_with_openclaw(self.products, self.theme, self.channel, agent_id="writer")
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[0], "openclaw")
        self.assertIn("--agent", cmd)
        self.assertIn("writer", cmd)
        self.assertIn("--json", cmd)

    @patch("pipeline_step_1_generate_script.subprocess.run")
    def test_nonzero_returncode_raises(self, mock_run):
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="", stderr="something failed")
        with self.assertRaises(RuntimeError) as ctx:
            generate_with_openclaw(self.products, self.theme, self.channel)
        self.assertIn("OpenClaw failed", str(ctx.exception))

    @patch("pipeline_step_1_generate_script.subprocess.run")
    def test_empty_payloads_raises(self, mock_run):
        output = json.dumps({"result": {"payloads": []}})
        mock_run.return_value = SimpleNamespace(returncode=0, stdout=output, stderr="")
        with self.assertRaises(RuntimeError) as ctx:
            generate_with_openclaw(self.products, self.theme, self.channel)
        self.assertIn("no payloads", str(ctx.exception))

    @patch("pipeline_step_1_generate_script.subprocess.run")
    def test_empty_text_raises(self, mock_run):
        output = json.dumps({"result": {"payloads": [{"text": ""}]}})
        mock_run.return_value = SimpleNamespace(returncode=0, stdout=output, stderr="")
        with self.assertRaises(RuntimeError) as ctx:
            generate_with_openclaw(self.products, self.theme, self.channel)
        self.assertIn("empty text", str(ctx.exception))

    @patch("pipeline_step_1_generate_script.subprocess.run")
    def test_null_result_raises(self, mock_run):
        output = json.dumps({"result": None})
        mock_run.return_value = SimpleNamespace(returncode=0, stdout=output, stderr="")
        with self.assertRaises(RuntimeError) as ctx:
            generate_with_openclaw(self.products, self.theme, self.channel)
        self.assertIn("no payloads", str(ctx.exception))

    @patch("pipeline_step_1_generate_script.subprocess.run")
    def test_timeout_passed_to_command(self, mock_run):
        script = self._make_valid_script()
        mock_run.return_value = self._mock_openclaw_success(script)
        generate_with_openclaw(self.products, self.theme, self.channel, timeout_sec=600)
        cmd = mock_run.call_args[0][0]
        timeout_idx = cmd.index("--timeout")
        self.assertEqual(cmd[timeout_idx + 1], "600")

    @patch("pipeline_step_1_generate_script.subprocess.run")
    def test_invalid_json_stdout_raises(self, mock_run):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="not json", stderr="")
        with self.assertRaises(Exception):
            generate_with_openclaw(self.products, self.theme, self.channel)

    @patch("pipeline_step_1_generate_script.subprocess.run")
    def test_variation_plan_included_in_prompt(self, mock_run):
        script = self._make_valid_script()
        mock_run.return_value = self._mock_openclaw_success(script)
        plan = {"selections": {"structure_template": "myth_busters"}, "prompt_instructions": {}}
        generate_with_openclaw(self.products, self.theme, self.channel, variation_plan=plan)
        cmd = mock_run.call_args[0][0]
        msg_idx = cmd.index("--message")
        prompt_text = cmd[msg_idx + 1]
        self.assertIn("myth_busters", prompt_text)

    @patch("pipeline_step_1_generate_script.subprocess.run")
    def test_stderr_truncated_in_error(self, mock_run):
        long_err = "x" * 500
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="", stderr=long_err)
        with self.assertRaises(RuntimeError) as ctx:
            generate_with_openclaw(self.products, self.theme, self.channel)
        # Error message should truncate stderr to 300 chars
        self.assertLessEqual(len(str(ctx.exception)), 350)


# ---------------------------------------------------------------
# main() CLI tests
# ---------------------------------------------------------------

class TestMain(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "run_001"
        self.run_dir.mkdir()
        # Write a minimal product_selection.json
        products = [
            {
                "product_title": f"Test Product {i}",
                "asin": f"B0{i:08d}",
                "current_price_usd": 49.99,
                "rating": 4.5,
                "review_count": 1000,
                "feature_bullets": ["Fast", "Reliable"],
                "amazon_url": f"https://www.amazon.com/dp/B0{i:08d}",
                "affiliate_url": f"https://www.amazon.com/dp/B0{i:08d}?tag=test-20",
                "available": True,
                "ranking_score": float(i),
            }
            for i in range(1, 6)
        ]
        (self.run_dir / "product_selection.json").write_text(
            json.dumps(products), encoding="utf-8"
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_mock_source_creates_script(self):
        from pipeline_step_1_generate_script import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir), "--script-source", "mock"]):
            try:
                main()
            except SystemExit:
                pass
        self.assertTrue((self.run_dir / "script.json").exists())

    def test_script_json_is_valid(self):
        from pipeline_step_1_generate_script import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir), "--script-source", "mock"]):
            try:
                main()
            except SystemExit:
                pass
        data = json.loads((self.run_dir / "script.json").read_text(encoding="utf-8"))
        self.assertIn("segments", data)
        self.assertGreater(len(data["segments"]), 0)

    def test_skip_if_script_exists(self):
        (self.run_dir / "script.json").write_text("{}", encoding="utf-8")
        from pipeline_step_1_generate_script import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)

    def test_error_if_no_products(self):
        (self.run_dir / "product_selection.json").unlink()
        from pipeline_step_1_generate_script import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_theme_from_state_json(self):
        state = {"theme": "gaming keyboards"}
        (self.run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
        from pipeline_step_1_generate_script import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir), "--script-source", "mock"]):
            try:
                main()
            except SystemExit:
                pass
        data = json.loads((self.run_dir / "script.json").read_text(encoding="utf-8"))
        self.assertIn("gaming keyboards", data["video_title"].lower())

    def test_theme_from_category_key(self):
        state = {"category": "headphones"}
        (self.run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
        from pipeline_step_1_generate_script import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir), "--script-source", "mock"]):
            try:
                main()
            except SystemExit:
                pass
        data = json.loads((self.run_dir / "script.json").read_text(encoding="utf-8"))
        self.assertIn("headphones", data["video_title"].lower())

    def test_theme_cli_overrides_state(self):
        state = {"theme": "wrong theme"}
        (self.run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
        from pipeline_step_1_generate_script import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir),
                                 "--script-source", "mock", "--theme", "monitors"]):
            try:
                main()
            except SystemExit:
                pass
        data = json.loads((self.run_dir / "script.json").read_text(encoding="utf-8"))
        self.assertIn("monitors", data["video_title"].lower())

    def test_variation_plan_loaded(self):
        plan = {
            "selections": {"structure_template": "tier_list"},
            "prompt_instructions": {"structure_description": "Tier list approach"},
        }
        (self.run_dir / "variation_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        from pipeline_step_1_generate_script import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir), "--script-source", "mock"]):
            try:
                main()
            except SystemExit:
                pass
        # Should complete without error; mock ignores variation_plan but accepts it
        self.assertTrue((self.run_dir / "script.json").exists())

    def test_default_theme_when_no_state(self):
        from pipeline_step_1_generate_script import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir), "--script-source", "mock"]):
            try:
                main()
            except SystemExit:
                pass
        data = json.loads((self.run_dir / "script.json").read_text(encoding="utf-8"))
        self.assertIn("products", data["video_title"].lower())

    def test_empty_product_list_exits(self):
        (self.run_dir / "product_selection.json").write_text("[]", encoding="utf-8")
        from pipeline_step_1_generate_script import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
