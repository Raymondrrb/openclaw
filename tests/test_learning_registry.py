"""Tests for rayvault/learning/registry.py — global event queries.

Covers: query_events, get_patterns, get_agent_learnings,
        get_promotion_candidates, get_weekly_summary.
Stdlib only.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from rayvault.learning.registry import (
    get_agent_learnings,
    get_patterns,
    get_promotion_candidates,
    get_weekly_summary,
    query_events,
)


def _write_events(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(events, indent=2), encoding="utf-8")


def _sample_events() -> list[dict]:
    """Create a realistic set of test events."""
    return [
        {
            "event_id": "le-001", "run_id": "r1",
            "timestamp": "2026-02-18T10:00:00Z",
            "severity": "FAIL", "component": "research",
            "symptom": "ASIN is accessories", "root_cause": "No price check",
            "fix_applied": "Added price validation",
            "verification": "Verified", "status": "applied",
            "video_id": "v038",
        },
        {
            "event_id": "le-002", "run_id": "r2",
            "timestamp": "2026-02-18T11:00:00Z",
            "severity": "WARN", "component": "assets",
            "symptom": "Phone ghost in BG Remove", "root_cause": "Ref had phone",
            "fix_applied": "Used drawbox",
            "verification": "", "status": "open",
            "video_id": "v039",
        },
        {
            "event_id": "le-003", "run_id": "r3",
            "timestamp": "2026-02-19T09:00:00Z",
            "severity": "FAIL", "component": "assets",
            "symptom": "Image hallucination", "root_cause": "Changed angle",
            "fix_applied": "Reverted angle",
            "verification": "Shape correct", "status": "verified",
            "video_id": "v039",
        },
        {
            "event_id": "le-004", "run_id": "r4",
            "timestamp": "2026-02-19T10:00:00Z",
            "severity": "BLOCKER", "component": "manifest",
            "symptom": "Render crash", "root_cause": "Missing media",
            "fix_applied": "Re-downloaded",
            "verification": "Render complete", "status": "applied",
            "video_id": "v040",
        },
        {
            "event_id": "le-005", "run_id": "r5",
            "timestamp": "2026-02-19T11:00:00Z",
            "severity": "FAIL", "component": "research",
            "symptom": "Duplicate evidence", "root_cause": "No price check",
            "fix_applied": "Added price validation",
            "verification": "Dedup works", "status": "applied",
            "video_id": "v041",
        },
    ]


class TestQueryEvents(unittest.TestCase):
    """Tests for query_events()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = Path(self.tmpdir) / "events.json"
        _write_events(self.path, _sample_events())

    def test_query_all(self):
        events = query_events(_path=self.path)
        self.assertEqual(len(events), 5)

    def test_filter_by_component(self):
        events = query_events(component="research", _path=self.path)
        self.assertEqual(len(events), 2)

    def test_filter_by_severity(self):
        events = query_events(severity="FAIL", _path=self.path)
        self.assertEqual(len(events), 3)

    def test_filter_by_video_id(self):
        events = query_events(video_id="v039", _path=self.path)
        self.assertEqual(len(events), 2)

    def test_filter_by_status(self):
        events = query_events(status="applied", _path=self.path)
        self.assertEqual(len(events), 3)

    def test_filter_by_date_from(self):
        events = query_events(date_from="2026-02-19T00:00:00Z", _path=self.path)
        self.assertEqual(len(events), 3)

    def test_filter_by_date_to(self):
        events = query_events(date_to="2026-02-18T23:59:59Z", _path=self.path)
        self.assertEqual(len(events), 2)

    def test_filter_combined(self):
        events = query_events(
            component="assets", severity="FAIL", _path=self.path,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_id"], "le-003")

    def test_no_match(self):
        events = query_events(component="tts", _path=self.path)
        self.assertEqual(len(events), 0)

    def test_empty_file(self):
        empty = Path(self.tmpdir) / "empty.json"
        events = query_events(_path=empty)
        self.assertEqual(len(events), 0)


class TestGetPatterns(unittest.TestCase):
    """Tests for get_patterns()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = Path(self.tmpdir) / "events.json"
        _write_events(self.path, _sample_events())

    def test_finds_patterns(self):
        patterns = get_patterns(min_count=2, _path=self.path)
        self.assertGreater(len(patterns), 0)

    def test_groups_by_component_and_root_cause(self):
        patterns = get_patterns(min_count=2, _path=self.path)
        # "research" + "No price check" appears 2x
        research_patterns = [p for p in patterns if p["component"] == "research"]
        self.assertEqual(len(research_patterns), 1)
        self.assertEqual(research_patterns[0]["count"], 2)

    def test_min_count_filter(self):
        patterns = get_patterns(min_count=3, _path=self.path)
        for p in patterns:
            self.assertGreaterEqual(p["count"], 3)

    def test_sorted_by_count_desc(self):
        patterns = get_patterns(min_count=2, _path=self.path)
        if len(patterns) > 1:
            self.assertGreaterEqual(patterns[0]["count"], patterns[-1]["count"])

    def test_pattern_fields(self):
        patterns = get_patterns(min_count=2, _path=self.path)
        if patterns:
            p = patterns[0]
            self.assertIn("component", p)
            self.assertIn("root_cause", p)
            self.assertIn("count", p)
            self.assertIn("severities", p)
            self.assertIn("video_ids", p)
            self.assertIn("latest", p)

    def test_empty_events(self):
        empty = Path(self.tmpdir) / "empty.json"
        _write_events(empty, [])
        patterns = get_patterns(min_count=2, _path=empty)
        self.assertEqual(len(patterns), 0)


class TestGetAgentLearnings(unittest.TestCase):
    """Tests for get_agent_learnings()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = Path(self.tmpdir) / "events.json"
        _write_events(self.path, _sample_events())

    def test_researcher_gets_research_events(self):
        events = get_agent_learnings("researcher", _path=self.path)
        self.assertGreater(len(events), 0)
        for e in events:
            self.assertIn(e["component"], ["research", "amazon", "products"])

    def test_dzine_producer_gets_assets_events(self):
        events = get_agent_learnings("dzine_producer", _path=self.path)
        self.assertGreater(len(events), 0)
        for e in events:
            self.assertIn(e["component"], ["assets", "dzine", "thumbnail"])

    def test_davinci_editor_gets_manifest(self):
        events = get_agent_learnings("davinci_editor", _path=self.path)
        self.assertGreater(len(events), 0)
        for e in events:
            self.assertIn(e["component"], ["manifest", "resolve", "render"])

    def test_unknown_agent_returns_empty(self):
        events = get_agent_learnings("nonexistent_agent", _path=self.path)
        self.assertEqual(len(events), 0)


class TestGetPromotionCandidates(unittest.TestCase):
    """Tests for get_promotion_candidates()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = Path(self.tmpdir) / "events.json"
        _write_events(self.path, _sample_events())

    def test_finds_candidates(self):
        # "No price check" root_cause appears 2x with status=applied
        candidates = get_promotion_candidates(threshold=2, _path=self.path)
        self.assertGreater(len(candidates), 0)

    def test_threshold_filter(self):
        candidates = get_promotion_candidates(threshold=10, _path=self.path)
        self.assertEqual(len(candidates), 0)

    def test_candidate_fields(self):
        candidates = get_promotion_candidates(threshold=2, _path=self.path)
        if candidates:
            c = candidates[0]
            self.assertIn("root_cause", c)
            self.assertIn("count", c)
            self.assertIn("components", c)
            self.assertIn("fix", c)
            self.assertIn("events", c)

    def test_only_applied_verified(self):
        # Event le-002 is "open" and should not count for promotion
        events = [
            {"event_id": "e1", "run_id": "r1", "timestamp": "2026-02-19T10:00:00Z",
             "severity": "FAIL", "component": "test", "root_cause": "same",
             "fix_applied": "fix", "status": "open"},
            {"event_id": "e2", "run_id": "r2", "timestamp": "2026-02-19T11:00:00Z",
             "severity": "FAIL", "component": "test", "root_cause": "same",
             "fix_applied": "fix", "status": "open"},
        ]
        path = Path(self.tmpdir) / "open_events.json"
        _write_events(path, events)
        candidates = get_promotion_candidates(threshold=2, _path=path)
        self.assertEqual(len(candidates), 0)

    def test_sorted_by_count_desc(self):
        candidates = get_promotion_candidates(threshold=1, _path=self.path)
        if len(candidates) > 1:
            self.assertGreaterEqual(candidates[0]["count"], candidates[-1]["count"])


class TestGetWeeklySummary(unittest.TestCase):
    """Tests for get_weekly_summary()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_no_reports_dir(self):
        import rayvault.learning.registry as mod
        orig = mod.REPORTS_DIR
        mod.REPORTS_DIR = Path(self.tmpdir) / "nonexistent"
        result = get_weekly_summary()
        self.assertIsNone(result)
        mod.REPORTS_DIR = orig

    def test_load_by_date(self):
        import rayvault.learning.registry as mod
        orig = mod.REPORTS_DIR
        report_dir = Path(self.tmpdir) / "reports"
        report_dir.mkdir()
        mod.REPORTS_DIR = report_dir

        report = {"events_total": 42, "period_days": 7}
        (report_dir / "weekly-2026-02-19.json").write_text(json.dumps(report))
        result = get_weekly_summary(date="2026-02-19")
        self.assertIsNotNone(result)
        self.assertEqual(result["events_total"], 42)
        mod.REPORTS_DIR = orig

    def test_load_latest(self):
        import rayvault.learning.registry as mod
        orig = mod.REPORTS_DIR
        report_dir = Path(self.tmpdir) / "reports"
        report_dir.mkdir()
        mod.REPORTS_DIR = report_dir

        (report_dir / "weekly-2026-02-18.json").write_text(
            json.dumps({"events_total": 10})
        )
        (report_dir / "weekly-2026-02-19.json").write_text(
            json.dumps({"events_total": 20})
        )
        result = get_weekly_summary()
        self.assertEqual(result["events_total"], 20)
        mod.REPORTS_DIR = orig

    def test_nonexistent_date_returns_none(self):
        import rayvault.learning.registry as mod
        orig = mod.REPORTS_DIR
        report_dir = Path(self.tmpdir) / "reports"
        report_dir.mkdir()
        mod.REPORTS_DIR = report_dir

        result = get_weekly_summary(date="2000-01-01")
        self.assertIsNone(result)
        mod.REPORTS_DIR = orig


if __name__ == "__main__":
    unittest.main()
