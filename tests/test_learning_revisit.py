"""Tests for tools/learning_revisit.py — periodic rule review.

Covers: phase_revalidate, phase_promotion_scan, phase_weekly_report,
        phase_tombstone_sweep, run_revisit orchestration.
Stdlib only.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.learning_revisit import (
    REPORTS_DIR,
    phase_promotion_scan,
    phase_revalidate,
    phase_tombstone_sweep,
    phase_weekly_report,
    run_revisit,
)
from tools.learning_apply import (
    CORE_AGENTS,
    apply_to_memory,
    init_agent_state,
    load_tombstones,
    tombstone_rule,
)
from tools.learning_event import LearningEvent


def _make_event(**overrides) -> LearningEvent:
    defaults = dict(
        event_id="le-test-00001",
        run_id="run001",
        timestamp="2026-02-19T12:00:00Z",
        severity="FAIL",
        component="research",
        symptom="test symptom",
        root_cause="test cause",
        fix_applied="test fix",
        verification="verified",
    )
    defaults.update(overrides)
    return LearningEvent(**defaults)


class TestPhaseRevalidate(unittest.TestCase):
    """Tests for phase_revalidate."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import tools.learning_apply as mod
        self._apply_mod = mod
        self._orig_dir = mod.AGENTS_STATE_DIR
        mod.AGENTS_STATE_DIR = Path(self.tmpdir)

    def tearDown(self):
        self._apply_mod.AGENTS_STATE_DIR = self._orig_dir

    def test_empty_memory(self):
        init_agent_state("researcher")
        result = phase_revalidate("researcher", 7)
        self.assertEqual(result["total_rules"], 0)
        self.assertEqual(result["stale"], [])
        self.assertEqual(result["conflicting"], [])

    def test_fresh_rules_not_stale(self):
        event = _make_event()
        apply_to_memory(event, "researcher")
        result = phase_revalidate("researcher", 7)
        self.assertEqual(result["total_rules"], 1)
        self.assertEqual(result["stale"], [])

    def test_old_rules_flagged_stale(self):
        event = _make_event()
        apply_to_memory(event, "researcher")
        # Manually set created to long ago
        from tools.learning_apply import _active_path
        path = _active_path("researcher")
        data = json.loads(path.read_text())
        data["rules"][0]["created"] = "2020-01-01T00:00:00Z"
        data["rules"][0]["applied_count"] = 1
        path.write_text(json.dumps(data))

        result = phase_revalidate("researcher", 7)
        self.assertEqual(len(result["stale"]), 1)

    def test_conflicting_rules_detected(self):
        e1 = _make_event(event_id="le-1", severity="FAIL", component="research")
        e2 = _make_event(event_id="le-2", severity="INFO", component="research")
        apply_to_memory(e1, "researcher")
        apply_to_memory(e2, "researcher")
        result = phase_revalidate("researcher", 7)
        # Both have same component but different severity → conflicting
        self.assertGreater(len(result["conflicting"]), 0)


class TestPhasePromotionScan(unittest.TestCase):
    """Tests for phase_promotion_scan."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import tools.learning_apply as mod
        self._apply_mod = mod
        self._orig_dir = mod.AGENTS_STATE_DIR
        mod.AGENTS_STATE_DIR = Path(self.tmpdir)

    def tearDown(self):
        self._apply_mod.AGENTS_STATE_DIR = self._orig_dir

    def test_no_candidates_when_empty(self):
        init_agent_state("researcher")
        result = phase_promotion_scan("researcher")
        self.assertEqual(result["candidates"], [])

    @patch("rayvault.policies.LEARNING_PROMOTION_THRESHOLD_OCCURRENCES", 2)
    def test_finds_candidates_above_threshold(self):
        event = _make_event()
        apply_to_memory(event, "researcher")
        apply_to_memory(event, "researcher")  # applied_count = 2
        result = phase_promotion_scan("researcher")
        self.assertEqual(len(result["candidates"]), 1)
        self.assertGreaterEqual(result["candidates"][0]["applied_count"], 2)

    @patch("rayvault.policies.LEARNING_PROMOTION_THRESHOLD_OCCURRENCES", 5)
    def test_below_threshold_no_candidates(self):
        event = _make_event()
        apply_to_memory(event, "researcher")
        result = phase_promotion_scan("researcher")
        self.assertEqual(result["candidates"], [])


class TestPhaseWeeklyReport(unittest.TestCase):
    """Tests for phase_weekly_report."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import tools.learning_apply as mod
        self._apply_mod = mod
        self._orig_dir = mod.AGENTS_STATE_DIR
        mod.AGENTS_STATE_DIR = Path(self.tmpdir)

        import tools.learning_revisit as rev_mod
        self._rev_mod = rev_mod
        self._orig_reports = rev_mod.REPORTS_DIR
        rev_mod.REPORTS_DIR = Path(self.tmpdir) / "reports"

    def tearDown(self):
        self._apply_mod.AGENTS_STATE_DIR = self._orig_dir
        self._rev_mod.REPORTS_DIR = self._orig_reports

    @patch("tools.learning_revisit.list_events")
    def test_generates_report(self, mock_list):
        mock_list.return_value = []
        # Init agent state for all core agents to avoid missing dirs
        for agent in CORE_AGENTS:
            init_agent_state(agent)

        report = phase_weekly_report("all", 7)
        self.assertIn("generated_at", report)
        self.assertEqual(report["events_total"], 0)
        self.assertEqual(report["events_recent"], 0)
        self.assertIn("agent_summaries", report)

        # Verify file written
        report_dir = Path(self.tmpdir) / "reports"
        reports = list(report_dir.glob("weekly-*.json"))
        self.assertEqual(len(reports), 1)

    @patch("tools.learning_revisit.list_events")
    def test_report_counts_by_severity(self, mock_list):
        mock_list.return_value = [
            LearningEvent(
                event_id="le-1", run_id="r1", timestamp="2026-02-19T12:00:00Z",
                severity="FAIL", component="research", symptom="s1",
                root_cause="c1", fix_applied="f1", verification="",
            ),
            LearningEvent(
                event_id="le-2", run_id="r2", timestamp="2026-02-19T12:01:00Z",
                severity="WARN", component="assets", symptom="s2",
                root_cause="c2", fix_applied="f2", verification="",
            ),
        ]
        for agent in CORE_AGENTS:
            init_agent_state(agent)

        report = phase_weekly_report("all", 7)
        self.assertEqual(report["events_total"], 2)
        self.assertEqual(report["by_severity"].get("FAIL", 0), 1)
        self.assertEqual(report["by_severity"].get("WARN", 0), 1)


class TestPhaseTombstoneSweep(unittest.TestCase):
    """Tests for phase_tombstone_sweep."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import tools.learning_apply as mod
        self._apply_mod = mod
        self._orig_dir = mod.AGENTS_STATE_DIR
        mod.AGENTS_STATE_DIR = Path(self.tmpdir)

    def tearDown(self):
        self._apply_mod.AGENTS_STATE_DIR = self._orig_dir

    def test_empty_sweep(self):
        init_agent_state("researcher")
        result = phase_tombstone_sweep("researcher", 30)
        self.assertEqual(result["kept"], 0)
        self.assertEqual(result["archived"], 0)

    def test_recent_tombstones_kept(self):
        event = _make_event()
        rule = apply_to_memory(event, "researcher")
        tombstone_rule("researcher", rule["rule_id"], "obsolete")
        result = phase_tombstone_sweep("researcher", 30)
        self.assertEqual(result["kept"], 1)
        self.assertEqual(result["archived"], 0)

    def test_old_tombstones_archived(self):
        event = _make_event()
        rule = apply_to_memory(event, "researcher")
        tombstone_rule("researcher", rule["rule_id"], "obsolete")
        # Manually backdate the tombstone
        from tools.learning_apply import _tombstones_path
        path = _tombstones_path("researcher")
        data = json.loads(path.read_text())
        data["tombstones"][0]["tombstoned_at"] = "2020-01-01T00:00:00Z"
        path.write_text(json.dumps(data))

        result = phase_tombstone_sweep("researcher", 30)
        self.assertEqual(result["archived"], 1)
        self.assertEqual(result["kept"], 0)


class TestRunRevisit(unittest.TestCase):
    """Tests for run_revisit orchestration."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import tools.learning_apply as mod
        self._apply_mod = mod
        self._orig_dir = mod.AGENTS_STATE_DIR
        mod.AGENTS_STATE_DIR = Path(self.tmpdir)

        import tools.learning_revisit as rev_mod
        self._rev_mod = rev_mod
        self._orig_reports = rev_mod.REPORTS_DIR
        rev_mod.REPORTS_DIR = Path(self.tmpdir) / "reports"

    def tearDown(self):
        self._apply_mod.AGENTS_STATE_DIR = self._orig_dir
        self._rev_mod.REPORTS_DIR = self._orig_reports

    @patch("tools.learning_revisit.list_events")
    def test_run_all_scope(self, mock_list):
        mock_list.return_value = []
        for agent in CORE_AGENTS:
            init_agent_state(agent)
        results = run_revisit("all", 7)
        self.assertEqual(results["scope"], "all")
        self.assertEqual(len(results["revalidation"]), len(CORE_AGENTS))
        self.assertEqual(len(results["promotions"]), len(CORE_AGENTS))
        self.assertIsNotNone(results["report"])

    @patch("tools.learning_revisit.list_events")
    def test_run_single_agent(self, mock_list):
        mock_list.return_value = []
        init_agent_state("researcher")
        results = run_revisit("researcher", 7)
        self.assertEqual(results["scope"], "researcher")
        self.assertIn("researcher", results["revalidation"])
        self.assertEqual(len(results["revalidation"]), 1)


if __name__ == "__main__":
    unittest.main()
