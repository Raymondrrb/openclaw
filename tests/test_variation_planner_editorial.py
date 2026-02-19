#!/usr/bin/env python3
"""Tests for editorial format moat in variation_planner."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from variation_planner import build_variation_plan  # type: ignore


class TestVariationPlannerEditorial(unittest.TestCase):
    def test_editorial_format_present(self):
        products = [
            {"rank": i, "title": f"Product {i}", "price": 120 + i, "rating": 4.5, "reviews": 1200}
            for i in range(1, 6)
        ]
        plan = build_variation_plan("run_editorial_test", "portable_monitors", products)
        selections = plan.get("selections", {})
        prompt = plan.get("prompt_instructions", {})
        self.assertIn("editorial_format", selections)
        self.assertIn("editorial_format", prompt)
        self.assertIn("editorial_format_rules", prompt)


if __name__ == "__main__":
    unittest.main()
