#!/usr/bin/env python3
"""Tests for tools/daily_go_nogo.py — daily Telegram notification utilities."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from daily_go_nogo import build_message, gate_emoji


# ---------------------------------------------------------------
# gate_emoji
# ---------------------------------------------------------------

class TestGateEmoji(unittest.TestCase):

    def test_true_returns_approved(self):
        self.assertEqual(gate_emoji(True), "approved")

    def test_false_returns_rejected(self):
        self.assertEqual(gate_emoji(False), "rejected")

    def test_none_returns_pending(self):
        self.assertEqual(gate_emoji(None), "pending")


# ---------------------------------------------------------------
# build_message
# ---------------------------------------------------------------

class TestBuildMessage(unittest.TestCase):

    def test_empty_runs(self):
        msg = build_message([])
        self.assertIn("Nenhum run encontrado", msg)
        self.assertIn("Daily GO/NO-GO", msg)

    def test_single_run_basic_fields(self):
        run = {
            "run_slug": "RUN_2026_02_15",
            "status": "draft_ready_waiting_gate_1",
            "category": "earbuds",
            "gate1_approved": None,
            "gate2_approved": None,
            "updated_at": "2026-02-15T10:00:00Z",
        }
        msg = build_message([run])
        self.assertIn("RUN_2026_02_15", msg)
        self.assertIn("earbuds", msg)
        self.assertIn("Gate 1: pending", msg)
        self.assertIn("Gate 2: pending", msg)

    def test_gate1_waiting_shows_approve_command(self):
        run = {
            "run_slug": "RUN_TEST",
            "status": "draft_ready_waiting_gate_1",
            "category": "speakers",
            "gate1_approved": None,
            "gate2_approved": None,
            "updated_at": "2026-02-15",
        }
        msg = build_message([run])
        self.assertIn("gate_decision.py", msg)
        self.assertIn("--gate gate1", msg)
        self.assertIn("approve", msg)
        self.assertIn("reject", msg)

    def test_gate2_waiting_shows_approve_command(self):
        run = {
            "run_slug": "RUN_TEST",
            "status": "assets_ready_waiting_gate_2",
            "category": "speakers",
            "gate1_approved": True,
            "gate2_approved": None,
            "updated_at": "2026-02-15",
        }
        msg = build_message([run])
        self.assertIn("--gate gate2", msg)

    def test_published_run(self):
        run = {
            "run_slug": "RUN_DONE",
            "status": "published",
            "category": "headphones",
            "gate1_approved": True,
            "gate2_approved": True,
            "updated_at": "2026-02-15",
        }
        msg = build_message([run])
        self.assertIn("publicado com sucesso", msg)

    def test_failed_run(self):
        run = {
            "run_slug": "RUN_FAIL",
            "status": "failed",
            "category": "monitors",
            "gate1_approved": True,
            "gate2_approved": None,
            "updated_at": "2026-02-15",
        }
        msg = build_message([run])
        self.assertIn("FAILED", msg)

    def test_other_status(self):
        run = {
            "run_slug": "RUN_X",
            "status": "rendering",
            "category": "tablets",
            "gate1_approved": True,
            "gate2_approved": True,
            "updated_at": "2026-02-15",
        }
        msg = build_message([run])
        self.assertIn("Nenhuma acao necessaria", msg)

    def test_multiple_runs_shows_count(self):
        runs = [
            {"run_slug": "A", "status": "published", "category": "a",
             "gate1_approved": True, "gate2_approved": True, "updated_at": ""},
            {"run_slug": "B", "status": "published", "category": "b",
             "gate1_approved": True, "gate2_approved": True, "updated_at": ""},
            {"run_slug": "C", "status": "published", "category": "c",
             "gate1_approved": True, "gate2_approved": True, "updated_at": ""},
        ]
        msg = build_message(runs)
        self.assertIn("+2 outros runs", msg)

    def test_reviewer_names(self):
        run = {
            "run_slug": "RUN_R",
            "status": "published",
            "category": "x",
            "gate1_approved": True,
            "gate2_approved": True,
            "gate1_reviewer": "alice",
            "gate2_reviewer": "bob",
            "updated_at": "",
        }
        msg = build_message([run])
        self.assertIn("alice", msg)
        self.assertIn("bob", msg)

    def test_missing_fields_default(self):
        run = {}
        msg = build_message([run])
        self.assertIn("?", msg)  # defaults to "?"


    def test_empty_slug_uses_default(self):
        run = {"run_slug": "", "status": "published", "category": "x",
               "gate1_approved": True, "gate2_approved": True, "updated_at": ""}
        msg = build_message([run])
        self.assertIsInstance(msg, str)

    def test_mixed_statuses(self):
        runs = [
            {"run_slug": "A", "status": "draft_ready_waiting_gate_1", "category": "a",
             "gate1_approved": None, "gate2_approved": None, "updated_at": ""},
            {"run_slug": "B", "status": "published", "category": "b",
             "gate1_approved": True, "gate2_approved": True, "updated_at": ""},
        ]
        msg = build_message(runs)
        # Shows first run details + count
        self.assertIn("Acao necessaria", msg)
        self.assertIn("+1 outros runs", msg)

    def test_gate1_approved_gate2_pending(self):
        run = {
            "run_slug": "R", "status": "assets_ready_waiting_gate_2",
            "category": "x", "gate1_approved": True, "gate2_approved": None,
            "updated_at": "",
        }
        msg = build_message(runs=[run])
        self.assertIn("Gate 1: approved", msg)
        self.assertIn("Gate 2: pending", msg)
        self.assertIn("--gate gate2", msg)

    def test_gate1_rejected(self):
        run = {
            "run_slug": "R", "status": "rejected",
            "category": "x", "gate1_approved": False, "gate2_approved": None,
            "updated_at": "",
        }
        msg = build_message([run])
        self.assertIn("Gate 1: rejected", msg)

    def test_only_two_runs(self):
        runs = [
            {"run_slug": "A", "status": "published", "category": "a",
             "gate1_approved": True, "gate2_approved": True, "updated_at": ""},
            {"run_slug": "B", "status": "published", "category": "b",
             "gate1_approved": True, "gate2_approved": True, "updated_at": ""},
        ]
        msg = build_message(runs)
        self.assertIn("+1 outros runs", msg)

    def test_no_reviewer_shows_dash(self):
        run = {
            "run_slug": "R", "status": "published", "category": "x",
            "gate1_approved": True, "gate2_approved": True, "updated_at": "",
        }
        msg = build_message([run])
        self.assertIn("reviewer: -", msg)


# ---------------------------------------------------------------
# gate_emoji edge cases
# ---------------------------------------------------------------

class TestGateEmojiEdgeCases(unittest.TestCase):

    def test_truthy_int_returns_approved(self):
        self.assertEqual(gate_emoji(1), "approved")

    def test_zero_returns_rejected(self):
        self.assertEqual(gate_emoji(0), "rejected")

    def test_empty_string_returns_rejected(self):
        self.assertEqual(gate_emoji(""), "rejected")

    def test_string_value_returns_approved(self):
        self.assertEqual(gate_emoji("yes"), "approved")


# ---------------------------------------------------------------
# build_message edge cases
# ---------------------------------------------------------------

class TestBuildMessageEdgeCases(unittest.TestCase):

    def test_four_runs_shows_plus_three(self):
        runs = [
            {"run_slug": f"R{i}", "status": "published", "category": f"cat_{i}",
             "gate1_approved": True, "gate2_approved": True, "updated_at": ""}
            for i in range(4)
        ]
        msg = build_message(runs)
        self.assertIn("+3 outros runs", msg)

    def test_updated_at_displayed(self):
        run = {
            "run_slug": "R", "status": "published", "category": "x",
            "gate1_approved": True, "gate2_approved": True,
            "updated_at": "2026-02-16T14:30:00Z",
        }
        msg = build_message([run])
        self.assertIn("2026-02-16", msg)

    def test_header_present(self):
        msg = build_message([])
        self.assertIn("Daily GO/NO-GO", msg)

    def test_both_gates_approved_published(self):
        run = {
            "run_slug": "SUCCESS", "status": "published", "category": "earbuds",
            "gate1_approved": True, "gate2_approved": True, "updated_at": "",
        }
        msg = build_message([run])
        self.assertIn("Gate 1: approved", msg)
        self.assertIn("Gate 2: approved", msg)


if __name__ == "__main__":
    unittest.main()
