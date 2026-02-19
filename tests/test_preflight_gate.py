"""Tests for tools/lib/preflight_gate.py.

Covers: can_run_assets, can_run_tts, cmd_day integration.
No API calls — pure logic tests with temp directories.
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

from tools.lib.video_paths import VideoPaths


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

def _make_products(overrides: list[dict] | None = None) -> dict:
    """Build a valid products.json dict, optionally overriding fields per rank."""
    products = []
    for rank in [5, 4, 3, 2, 1]:
        p = {
            "rank": rank,
            "name": f"Product {rank}",
            "asin": f"B0{rank}ASIN",
            "affiliate_url": f"https://amzn.to/{rank}abc",
            "positioning": f"best for rank {rank}",
            "benefits": [f"Benefit A"],
            "downside": "Minor issue",
            "evidence": [],
        }
        if overrides:
            for ov in overrides:
                if ov.get("rank") == rank:
                    p.update(ov)
        products.append(p)
    return {"keyword": "test niche", "products": products}


VALID_PRODUCTS = _make_products()

SAMPLE_REPORT = """\
# Research Report

## Wirecutter
https://www.nytimes.com/wirecutter/best-earbuds

## RTINGS
https://www.rtings.com/headphones/reviews

## PCMag
https://www.pcmag.com/picks/best-earbuds

## Amazon
https://www.amazon.com/dp/B01ASIN
"""

BAD_REPORT = """\
# Research Report

https://www.nytimes.com/wirecutter/best-earbuds
https://www.bestbuy.com/earbuds
"""


# ---------------------------------------------------------------------------
# Tests: can_run_assets
# ---------------------------------------------------------------------------


class TestCanRunAssets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.videos_base = Path(self.tmp.name)
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", self.videos_base)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def _setup(self, video_id, products=None, report=None):
        paths = VideoPaths(video_id)
        paths.ensure_dirs()
        if products is not None:
            paths.products_json.write_text(json.dumps(products), encoding="utf-8")
        if report is not None:
            paths.research_report.write_text(report, encoding="utf-8")
        return paths

    def test_no_products(self):
        from tools.lib.preflight_gate import can_run_assets
        self._setup("t1")  # no products.json
        ok, reason = can_run_assets("t1")
        self.assertFalse(ok)
        self.assertIn("products.json", reason)

    def test_missing_asin(self):
        from tools.lib.preflight_gate import can_run_assets
        products = _make_products([{"rank": 3, "asin": ""}])
        self._setup("t2", products=products)
        ok, reason = can_run_assets("t2")
        self.assertFalse(ok)
        self.assertIn("ASIN", reason)

    def test_missing_affiliate(self):
        from tools.lib.preflight_gate import can_run_assets
        products = _make_products([{"rank": 2, "affiliate_url": ""}])
        self._setup("t3", products=products)
        ok, reason = can_run_assets("t3")
        self.assertFalse(ok)
        self.assertIn("affiliate_url", reason)

    def test_valid(self):
        from tools.lib.preflight_gate import can_run_assets
        self._setup("t4", products=VALID_PRODUCTS, report=SAMPLE_REPORT)
        ok, reason = can_run_assets("t4")
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_no_report_warns_not_blocks(self):
        from tools.lib.preflight_gate import can_run_assets
        self._setup("t5", products=VALID_PRODUCTS)
        # No research_report.md — should still pass (report is optional)
        ok, reason = can_run_assets("t5")
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_bad_domain_in_report(self):
        from tools.lib.preflight_gate import can_run_assets
        self._setup("t6", products=VALID_PRODUCTS, report=BAD_REPORT)
        ok, reason = can_run_assets("t6")
        self.assertFalse(ok)
        self.assertIn("bestbuy.com", reason)

    def test_wrong_product_count(self):
        from tools.lib.preflight_gate import can_run_assets
        data = {"keyword": "test", "products": [{"rank": 1, "asin": "B01", "affiliate_url": "x"}]}
        self._setup("t7", products=data)
        ok, reason = can_run_assets("t7")
        self.assertFalse(ok)
        self.assertIn("1 products", reason)


# ---------------------------------------------------------------------------
# Tests: can_run_tts
# ---------------------------------------------------------------------------


class TestCanRunTts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.videos_base = Path(self.tmp.name)
        self.patcher = patch("tools.lib.video_paths.VIDEOS_BASE", self.videos_base)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def _setup(self, video_id, script_final=False, review_notes=False):
        paths = VideoPaths(video_id)
        paths.ensure_dirs()
        if script_final:
            paths.script_final.parent.mkdir(parents=True, exist_ok=True)
            paths.script_final.write_text("Final script content", encoding="utf-8")
        if review_notes:
            paths.script_review_notes.parent.mkdir(parents=True, exist_ok=True)
            paths.script_review_notes.write_text("# Review notes", encoding="utf-8")
        return paths

    def test_no_script_final(self):
        from tools.lib.preflight_gate import can_run_tts
        self._setup("tts1")
        ok, reason = can_run_tts("tts1")
        self.assertFalse(ok)
        self.assertIn("script_final", reason)

    def test_no_review_notes(self):
        from tools.lib.preflight_gate import can_run_tts
        self._setup("tts2", script_final=True)
        ok, reason = can_run_tts("tts2")
        self.assertFalse(ok)
        self.assertIn("review", reason)

    def test_valid(self):
        from tools.lib.preflight_gate import can_run_tts
        self._setup("tts3", script_final=True, review_notes=True)
        ok, reason = can_run_tts("tts3")
        self.assertTrue(ok)
        self.assertEqual(reason, "")


# ---------------------------------------------------------------------------
# Tests: cmd_day integration
# ---------------------------------------------------------------------------


class TestCmdDay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.videos_base = Path(self.tmp.name)
        self.patchers = [
            patch("tools.lib.video_paths.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status._cache", {}),
            patch("tools.lib.notify.send_telegram", return_value=False),
            patch("tools.pipeline._run_learning_gate", return_value=None),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    def test_day_runs_to_script(self):
        """Day command with mocked research + script should succeed."""
        import argparse
        from tools.pipeline import cmd_day, EXIT_OK

        # Mock the research stage to avoid real browser calls
        def fake_cmd_research(args):
            # Simulate successful research: write products.json
            paths = VideoPaths(args.video_id)
            products = _make_products()
            products["sources_used"] = ["Wirecutter", "RTINGS", "PCMag"]
            paths.products_json.write_text(json.dumps(products), encoding="utf-8")
            return 0

        # Mock the script stage to avoid API calls
        def fake_cmd_script(args):
            paths = VideoPaths(args.video_id)
            paths.script_txt.parent.mkdir(parents=True, exist_ok=True)
            paths.script_txt.write_text("[HOOK]\nTest script\n", encoding="utf-8")
            return 0

        with patch("tools.pipeline.cmd_research", side_effect=fake_cmd_research), \
             patch("tools.pipeline.cmd_script", side_effect=fake_cmd_script):
            args = argparse.Namespace(
                video_id="test-day",
                niche="wireless earbuds",
                force=False,
            )
            rc = cmd_day(args)

        # Day should return OK (script auto-generated)
        self.assertEqual(rc, EXIT_OK)

        # Brief should have been generated
        paths = VideoPaths("test-day")
        self.assertTrue(paths.manual_brief.is_file())
        content = paths.manual_brief.read_text()
        self.assertIn("WIRELESS EARBUDS", content.upper())


if __name__ == "__main__":
    unittest.main()
