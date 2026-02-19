#!/usr/bin/env python3
"""Tests for rayvault/compliance_contract.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rayvault.compliance_contract import run_contract
from rayvault.io import atomic_write_json


def _base_assets_manifest() -> dict:
    return {
        "assets": [
            {
                "product_rank": i,
                "files": {
                    "product_ref_image": f"assets/product_{i}/ref_amazon.jpg",
                    "dzine_images": [f"assets/product_{i}/variant_01.png"],
                },
            }
            for i in range(1, 6)
        ]
    }


def _base_products(valid_link: bool = True, use_amzn_short: bool = False) -> dict:
    link = "https://www.amazon.com/dp/B0TEST123?tag=rayviews-20"
    if use_amzn_short:
        link = "https://amzn.to/3OjKBMV"
    elif not valid_link:
        link = "https://bit.ly/abc123"
    return {
        "products": [
            {
                "rank": i,
                "asin": f"B0TEST{i}",
                "affiliate_url": link,
                "product_url": f"https://www.amazon.com/dp/B0TEST{i}",
            }
            for i in range(1, 6)
        ]
    }


def _script(with_intro_disclosure: bool) -> dict:
    intro = "Quick disclosure: affiliate links may earn me a commission at no extra cost to you."
    if not with_intro_disclosure:
        intro = "I tested five products this week and ranked them by value."
    return {
        "structure": [
            {"id": "hook", "type": "NARRATION", "voice_text": intro},
            {"id": "p1", "type": "PRODUCT_BLOCK", "product_rank": 1, "voice_text": "Product details."},
        ]
    }


class TestComplianceContract(unittest.TestCase):
    def _write_base_files(
        self,
        run_dir: Path,
        *,
        intro: bool = True,
        valid_link: bool = True,
        use_amzn_short: bool = False,
    ):
        atomic_write_json(run_dir / "script.json", _script(intro))
        atomic_write_json(
            run_dir / "products.json",
            _base_products(valid_link=valid_link, use_amzn_short=use_amzn_short),
        )
        atomic_write_json(run_dir / "assets_manifest.json", _base_assets_manifest())
        (run_dir / "rayvault").mkdir(parents=True, exist_ok=True)
        atomic_write_json(run_dir / "rayvault" / "00_manifest.json", {"run_id": "test"})

    def test_ok_contract(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            self._write_base_files(run_dir, intro=True, valid_link=True)
            report = run_contract(run_dir)
            self.assertIn(report["status"], {"OK", "WARN"})
            self.assertTrue((run_dir / "compliance_report.json").exists())
            self.assertTrue((run_dir / "upload" / "disclosure_snippets.json").exists())
            self.assertTrue((run_dir / "upload" / "pinned_comment.txt").exists())

    def test_fail_missing_intro_disclosure(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            self._write_base_files(run_dir, intro=False, valid_link=True)
            report = run_contract(run_dir)
            self.assertEqual(report["status"], "FAIL")

    def test_fail_shortener_link(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            self._write_base_files(run_dir, intro=True, valid_link=False)
            report = run_contract(run_dir)
            self.assertEqual(report["status"], "FAIL")
            self.assertGreater(len(report["link_clarity"]["violations"]), 0)

    def test_allow_amzn_short_link(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            self._write_base_files(run_dir, intro=True, use_amzn_short=True)
            report = run_contract(run_dir)
            self.assertIn(report["status"], {"OK", "WARN"})
            self.assertEqual(len(report["link_clarity"]["violations"]), 0)


if __name__ == "__main__":
    unittest.main()
