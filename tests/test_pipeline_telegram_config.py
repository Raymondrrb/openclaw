#!/usr/bin/env python3
"""Tests for Telegram approval helpers in tools/pipeline.py."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.pipeline import (  # noqa: E402
    _ensure_telegram_stage_approvals,
    _parse_telegram_stages,
    _telegram_approvals_enabled,
)


class TestTelegramStages(unittest.TestCase):
    def test_parse_stages_filters_unknown_and_dedupes(self):
        out = _parse_telegram_stages("niche,products,unknown,gate1,products,assets")
        self.assertEqual(out, ["niche", "products", "gate1", "assets"])

    def test_parse_stages_empty(self):
        self.assertEqual(_parse_telegram_stages(""), [])


class TestTelegramEnabled(unittest.TestCase):
    def test_enabled_from_args(self):
        class A:
            telegram_approvals = True

        self.assertTrue(_telegram_approvals_enabled(A()))

    def test_enabled_from_env(self):
        class A:
            telegram_approvals = False

        with unittest.mock.patch.dict(os.environ, {"PIPELINE_TELEGRAM_APPROVALS": "1"}, clear=False):
            self.assertTrue(_telegram_approvals_enabled(A()))


class TestEnsureStageApprovals(unittest.TestCase):
    def test_injects_defaults(self):
        cfg = {}
        changed = _ensure_telegram_stage_approvals(cfg)
        self.assertTrue(changed)
        approvals = cfg.get("stage_approvals", {})
        self.assertEqual(sorted(approvals.keys()), ["assets", "niche", "products"])
        self.assertEqual(approvals["niche"]["status"], "pending")

    def test_normalizes_invalid_status(self):
        cfg = {"stage_approvals": {"niche": {"status": "INVALID"}}}
        _ensure_telegram_stage_approvals(cfg)
        self.assertEqual(cfg["stage_approvals"]["niche"]["status"], "pending")


if __name__ == "__main__":
    unittest.main()

