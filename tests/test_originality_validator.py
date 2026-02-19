#!/usr/bin/env python3
"""Tests for rayvault/originality_validator.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rayvault.io import atomic_write_json
from rayvault.originality_validator import run_validation


def _script_ok() -> dict:
    structure = [
        {
            "id": "hook",
            "type": "NARRATION",
            "voice_text": "I tested these five products side by side, and there are clear trade-offs.",
        }
    ]
    for rank in range(1, 6):
        structure.append(
            {
                "id": f"p{rank}",
                "type": "PRODUCT_BLOCK",
                "product_rank": rank,
                "segments": [
                    {
                        "kind": "NARRATION",
                        "role": "evidence",
                        "voice_text": (
                            f"For product {rank}, I measured startup delay in milliseconds and compared it to two competitors. "
                            f"In my test log, product {rank} kept stable performance after a longer session."
                        ),
                    },
                    {
                        "kind": "NARRATION",
                        "voice_text": (
                            f"My take for product {rank}: I think this is worth it only for a specific workflow profile. "
                            f"Skip if you need portability and ultra-light travel setup."
                        ),
                    },
                ],
            }
        )
    return {"structure": structure}


def _products() -> dict:
    return {
        "products": [
            {"rank": i, "asin": f"B0TEST{i}", "title": f"Product {i}", "price": 149.0}
            for i in range(1, 6)
        ]
    }


class TestOriginalityValidator(unittest.TestCase):
    def test_ok_script(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            atomic_write_json(run_dir / "script.json", _script_ok())
            atomic_write_json(run_dir / "products.json", _products())
            report = run_validation(run_dir)
            self.assertIn(report["status"], {"OK", "WARN"})
            self.assertIn("metrics", report)

    def test_fail_missing_files(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            report = run_validation(run_dir)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["exit_code"], 2)

    def test_fail_repetitive_no_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            repetitive = {
                "structure": [
                    {
                        "id": f"p{i}",
                        "type": "PRODUCT_BLOCK",
                        "product_rank": i,
                        "voice_text": "This one is great for everyone. This one is great for everyone.",
                    }
                    for i in range(1, 6)
                ]
            }
            atomic_write_json(run_dir / "script.json", repetitive)
            atomic_write_json(run_dir / "products.json", _products())
            report = run_validation(run_dir)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["exit_code"], 2)


if __name__ == "__main__":
    unittest.main()
