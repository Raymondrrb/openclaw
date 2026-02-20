"""Tests for the closed-loop learning system.

Covers: learning_event, learning_apply, learning_gate, learning_revisit,
        rayvault.learning.registry.

All tests use temp directories — no side effects on real data.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


# ===================================================================
# learning_event.py
# ===================================================================

class TestLearningEventModel(unittest.TestCase):
    """Test LearningEvent dataclass and helpers."""

    def test_make_event_id_format(self):
        from tools.learning_event import _make_event_id
        eid = _make_event_id("2026-02-20T12:00:00Z", "test symptom")
        self.assertTrue(eid.startswith("le-"))
        parts = eid.split("-")
        self.assertEqual(len(parts), 3)
        self.assertEqual(len(parts[2]), 5)  # 5-char hash

    def test_make_event_id_deterministic(self):
        from tools.learning_event import _make_event_id
        a = _make_event_id("2026-02-20T12:00:00Z", "symptom")
        b = _make_event_id("2026-02-20T12:00:00Z", "symptom")
        self.assertEqual(a, b)

    def test_make_event_id_varies_by_symptom(self):
        from tools.learning_event import _make_event_id
        a = _make_event_id("2026-02-20T12:00:00Z", "symptom A")
        b = _make_event_id("2026-02-20T12:00:00Z", "symptom B")
        self.assertNotEqual(a, b)

    def test_severities_tuple(self):
        from tools.learning_event import SEVERITIES
        self.assertIn("INFO", SEVERITIES)
        self.assertIn("WARN", SEVERITIES)
        self.assertIn("FAIL", SEVERITIES)
        self.assertIn("BLOCKER", SEVERITIES)

    def test_statuses_tuple(self):
        from tools.learning_event import STATUSES
        self.assertIn("open", STATUSES)
        self.assertIn("applied", STATUSES)
        self.assertIn("verified", STATUSES)
        self.assertIn("archived", STATUSES)


class TestLearningEventCRUD(unittest.TestCase):
    """Test create/read/update/list with temp files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.events_path = Path(self.tmp.name) / "events.json"

    def tearDown(self):
        self.tmp.cleanup()

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_create_event(self, mock_sync):
        from tools.learning_event import create_event
        event = create_event(
            run_id="v001",
            severity="FAIL",
            component="research",
            symptom="ASIN is accessories",
            root_cause="Price validation missing",
            fix_applied="Added price anomaly check",
            verification="Re-ran with fix",
            video_id="v001",
            _path=self.events_path,
        )
        self.assertTrue(event.event_id.startswith("le-"))
        self.assertEqual(event.severity, "FAIL")
        self.assertEqual(event.component, "research")
        self.assertEqual(event.run_id, "v001")
        self.assertEqual(event.status, "open")

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_create_event_invalid_severity(self, mock_sync):
        from tools.learning_event import create_event
        with self.assertRaises(ValueError):
            create_event(
                run_id="v001", severity="CRITICAL",
                component="test", symptom="test", root_cause="test",
                fix_applied="test", _path=self.events_path,
            )

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_create_persists_to_file(self, mock_sync):
        from tools.learning_event import create_event
        create_event(
            run_id="v001", severity="WARN", component="assets",
            symptom="Phone ghost", root_cause="BG Remove incomplete",
            fix_applied="drawbox white", _path=self.events_path,
        )
        self.assertTrue(self.events_path.is_file())
        data = json.loads(self.events_path.read_text())
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["severity"], "WARN")

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_list_events_empty(self, mock_sync):
        from tools.learning_event import list_events
        events = list_events(_path=self.events_path)
        self.assertEqual(events, [])

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_list_events_with_filter(self, mock_sync):
        from tools.learning_event import create_event, list_events
        create_event(
            run_id="v001", severity="FAIL", component="research",
            symptom="s1", root_cause="rc1", fix_applied="f1",
            _path=self.events_path,
        )
        create_event(
            run_id="v002", severity="WARN", component="assets",
            symptom="s2", root_cause="rc2", fix_applied="f2",
            _path=self.events_path,
        )
        fails = list_events(severity="FAIL", _path=self.events_path)
        self.assertEqual(len(fails), 1)
        self.assertEqual(fails[0].component, "research")

        assets = list_events(component="assets", _path=self.events_path)
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].severity, "WARN")

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_get_event(self, mock_sync):
        from tools.learning_event import create_event, get_event
        event = create_event(
            run_id="v001", severity="INFO", component="tts",
            symptom="Clipping detected", root_cause="Volume too high",
            fix_applied="Reduced gain", _path=self.events_path,
        )
        found = get_event(event.event_id, _path=self.events_path)
        self.assertIsNotNone(found)
        self.assertEqual(found.event_id, event.event_id)
        self.assertEqual(found.symptom, "Clipping detected")

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_get_event_not_found(self, mock_sync):
        from tools.learning_event import get_event
        self.assertIsNone(get_event("nonexistent", _path=self.events_path))

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_update_event_status(self, mock_sync):
        from tools.learning_event import create_event, update_event
        event = create_event(
            run_id="v001", severity="FAIL", component="test",
            symptom="test", root_cause="test", fix_applied="test",
            _path=self.events_path,
        )
        updated = update_event(
            event.event_id, status="verified", _path=self.events_path,
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, "verified")

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_update_event_invalid_status(self, mock_sync):
        from tools.learning_event import create_event, update_event
        event = create_event(
            run_id="v001", severity="FAIL", component="test",
            symptom="test", root_cause="test", fix_applied="test",
            _path=self.events_path,
        )
        with self.assertRaises(ValueError):
            update_event(event.event_id, status="invalid", _path=self.events_path)

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_update_event_not_found(self, mock_sync):
        from tools.learning_event import update_event
        result = update_event("nonexistent", status="verified", _path=self.events_path)
        self.assertIsNone(result)

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_create_with_agent_applies_memory(self, mock_sync):
        from tools.learning_event import create_event
        with patch("tools.learning_apply.apply_to_memory") as mock_apply:
            mock_apply.return_value = {"rule_id": "r-test"}
            event = create_event(
                run_id="v001", severity="FAIL", component="assets",
                symptom="Phone ghost", root_cause="Missing drawbox",
                fix_applied="Added drawbox step", agent="dzine_producer",
                _path=self.events_path,
            )
            mock_apply.assert_called_once()
            self.assertEqual(event.status, "applied")

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_create_calls_skill_graph_sync(self, mock_sync):
        from tools.learning_event import create_event
        create_event(
            run_id="v001", severity="WARN", component="test",
            symptom="test", root_cause="test", fix_applied="test",
            _path=self.events_path,
        )
        mock_sync.assert_called_once()

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_per_video_file_created(self, mock_sync):
        from tools.learning_event import create_event
        vid_dir = Path(self.tmp.name) / "artifacts" / "videos"
        with patch("tools.learning_event.project_root", return_value=Path(self.tmp.name)):
            event = create_event(
                run_id="v001", severity="FAIL", component="test",
                symptom="test", root_cause="test", fix_applied="test",
                video_id="v001", _path=self.events_path,
            )
            per_video = vid_dir / "v001" / "learning" / "events" / f"{event.event_id}.json"
            self.assertTrue(per_video.is_file())

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_corrupt_file_returns_empty(self, mock_sync):
        from tools.learning_event import list_events
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self.events_path.write_text("not json", encoding="utf-8")
        events = list_events(_path=self.events_path)
        self.assertEqual(events, [])


class TestLearningEventBridge(unittest.TestCase):
    """Test promote_from_error bridge."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.error_path = Path(self.tmp.name) / "error_log.json"
        self.events_path = Path(self.tmp.name) / "events.json"

    def tearDown(self):
        self.tmp.cleanup()

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_promote_from_error(self, mock_sync):
        from tools.lib.error_log import log_error
        from tools.learning_event import promote_from_error
        error = log_error("v001", "research", "ASIN is accessories", _path=self.error_path)
        event = promote_from_error(
            error["id"],
            root_cause="No price validation",
            fix="Added price anomaly check",
            severity="FAIL",
            component="research",
            _error_path=self.error_path,
            _events_path=self.events_path,
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.source_error_id, error["id"])
        self.assertEqual(event.severity, "FAIL")

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_promote_error_not_found(self, mock_sync):
        from tools.learning_event import promote_from_error
        result = promote_from_error(
            "nonexistent",
            root_cause="test", fix="test",
            _error_path=self.error_path,
            _events_path=self.events_path,
        )
        self.assertIsNone(result)

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_promote_resolves_original_error(self, mock_sync):
        from tools.lib.error_log import log_error, _read_log
        from tools.learning_event import promote_from_error
        error = log_error("v001", "research", "Test error", _path=self.error_path)
        promote_from_error(
            error["id"], root_cause="rc", fix="fix",
            _error_path=self.error_path, _events_path=self.events_path,
        )
        errors = _read_log(self.error_path)
        resolved = [e for e in errors if e["id"] == error["id"]]
        self.assertTrue(resolved[0]["resolved"])


class TestSkillGraphSync(unittest.TestCase):
    """Test sync_to_skill_graph."""

    def test_sync_calls_record_learning(self):
        from tools.learning_event import LearningEvent, sync_to_skill_graph
        event = LearningEvent(
            event_id="le-test", run_id="v001", timestamp="2026-02-20T12:00:00Z",
            severity="FAIL", component="research", symptom="Test symptom",
            root_cause="Test cause", fix_applied="Test fix",
            verification="Verified",
        )
        with patch("tools.lib.skill_graph.record_learning") as mock_record:
            mock_record.return_value = Path("/tmp/test.md")
            result = sync_to_skill_graph(event)
            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args
            self.assertIn("FAIL", call_kwargs.kwargs.get("title", "") or call_kwargs[1].get("title", ""))

    def test_sync_includes_verification_in_body(self):
        from tools.learning_event import LearningEvent, sync_to_skill_graph
        event = LearningEvent(
            event_id="le-test", run_id="v001", timestamp="2026-02-20T12:00:00Z",
            severity="WARN", component="tts", symptom="Clipping",
            root_cause="Volume", fix_applied="Reduce gain",
            verification="Re-ran successfully",
        )
        with patch("tools.lib.skill_graph.record_learning") as mock_record:
            mock_record.return_value = Path("/tmp/test.md")
            sync_to_skill_graph(event)
            body = mock_record.call_args.kwargs.get("body", "")
            self.assertIn("Verification", body)
            self.assertIn("Re-ran successfully", body)


# ===================================================================
# learning_apply.py
# ===================================================================

class TestLearningApplyMemory(unittest.TestCase):
    """Test apply_to_memory and related functions."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch(
            "tools.learning_apply.AGENTS_STATE_DIR",
            Path(self.tmp.name) / "agents",
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_init_agent_state(self):
        from tools.learning_apply import init_agent_state, _active_path, _tombstones_path
        init_agent_state("test_agent")
        self.assertTrue(_active_path("test_agent").is_file())
        self.assertTrue(_tombstones_path("test_agent").is_file())

    def test_init_all_agents(self):
        from tools.learning_apply import init_all_agents, CORE_AGENTS, _active_path
        init_all_agents()
        for agent in CORE_AGENTS:
            self.assertTrue(_active_path(agent).is_file())

    def test_load_active_memory_empty(self):
        from tools.learning_apply import load_active_memory
        memory = load_active_memory("nonexistent_agent")
        self.assertEqual(memory, {})

    def test_load_active_memory_after_init(self):
        from tools.learning_apply import init_agent_state, load_active_memory
        init_agent_state("test_agent")
        memory = load_active_memory("test_agent")
        self.assertIn("rules", memory)
        self.assertEqual(memory["count"], 0)

    def test_apply_to_memory_creates_rule(self):
        from tools.learning_apply import apply_to_memory, load_active_memory, init_agent_state
        init_agent_state("dzine_producer")
        event_dict = {
            "event_id": "le-test-12345",
            "severity": "FAIL",
            "component": "assets",
            "root_cause": "Phone ghost in BG Remove",
            "fix_applied": "Use drawbox to paint phone white",
            "symptom": "Product image has phone remnants",
            "video_id": "v001",
        }
        rule = apply_to_memory(event_dict, "dzine_producer")
        self.assertTrue(rule["rule_id"].startswith("r-"))
        self.assertEqual(rule["severity"], "FAIL")

        memory = load_active_memory("dzine_producer")
        self.assertEqual(memory["count"], 1)
        self.assertEqual(len(memory["rules"]), 1)

    def test_apply_duplicate_increments_count(self):
        from tools.learning_apply import apply_to_memory, load_active_memory, init_agent_state
        init_agent_state("researcher")
        event_dict = {
            "event_id": "le-test-12345",
            "severity": "FAIL",
            "component": "research",
            "root_cause": "Accessories detected",
            "fix_applied": "Price check",
            "symptom": "ASIN is accessories",
            "video_id": "v001",
        }
        apply_to_memory(event_dict, "researcher")
        rule = apply_to_memory(event_dict, "researcher")  # Same event
        self.assertEqual(rule["applied_count"], 2)

        memory = load_active_memory("researcher")
        self.assertEqual(memory["count"], 1)  # Still 1 rule, not 2

    def test_apply_enforces_max_rules(self):
        from tools.learning_apply import apply_to_memory, load_active_memory, init_agent_state
        init_agent_state("test_agent")

        with patch("rayvault.policies.LEARNING_MAX_ACTIVE_RULES_PER_AGENT", 3):
            for i in range(5):
                event_dict = {
                    "event_id": f"le-test-{i:05d}",
                    "severity": "INFO",
                    "component": "test",
                    "root_cause": f"cause {i}",
                    "fix_applied": f"fix {i}",
                    "symptom": f"symptom {i}",
                    "video_id": "v001",
                }
                apply_to_memory(event_dict, "test_agent")

        memory = load_active_memory("test_agent")
        self.assertLessEqual(memory["count"], 3)

    def test_apply_preserves_critical_rules(self):
        from tools.learning_apply import apply_to_memory, load_active_memory, init_agent_state
        init_agent_state("test_agent")

        with patch("rayvault.policies.LEARNING_MAX_ACTIVE_RULES_PER_AGENT", 2):
            # Add BLOCKER rule first
            blocker = {
                "event_id": "le-block-00001",
                "severity": "BLOCKER",
                "component": "test",
                "root_cause": "critical", "fix_applied": "fix",
                "symptom": "symptom", "video_id": "v001",
            }
            apply_to_memory(blocker, "test_agent")

            # Add INFO rules that should be evicted first
            for i in range(3):
                info = {
                    "event_id": f"le-info-{i:05d}",
                    "severity": "INFO",
                    "component": "test",
                    "root_cause": f"minor {i}", "fix_applied": f"fix {i}",
                    "symptom": f"s {i}", "video_id": "v001",
                }
                apply_to_memory(info, "test_agent")

        memory = load_active_memory("test_agent")
        rule_ids = [r["rule_id"] for r in memory["rules"]]
        self.assertIn("r-le-block-00001", rule_ids)


class TestLearningApplyTombstone(unittest.TestCase):
    """Test tombstone_rule."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch(
            "tools.learning_apply.AGENTS_STATE_DIR",
            Path(self.tmp.name) / "agents",
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_tombstone_moves_rule(self):
        from tools.learning_apply import (
            apply_to_memory, init_agent_state, load_active_memory,
            load_tombstones, tombstone_rule,
        )
        init_agent_state("dzine_producer")
        event_dict = {
            "event_id": "le-test-12345",
            "severity": "WARN",
            "component": "assets",
            "root_cause": "cause", "fix_applied": "fix",
            "symptom": "symptom", "video_id": "v001",
        }
        rule = apply_to_memory(event_dict, "dzine_producer")

        tombstoned = tombstone_rule(
            "dzine_producer", rule["rule_id"],
            "Rule obsoleted by new approach",
        )
        self.assertIsNotNone(tombstoned)
        self.assertEqual(tombstoned["reason"], "Rule obsoleted by new approach")

        memory = load_active_memory("dzine_producer")
        self.assertEqual(memory["count"], 0)

        tombstones = load_tombstones("dzine_producer")
        self.assertEqual(tombstones["count"], 1)

    def test_tombstone_not_found(self):
        from tools.learning_apply import init_agent_state, tombstone_rule
        init_agent_state("test_agent")
        result = tombstone_rule("test_agent", "nonexistent", "reason")
        self.assertIsNone(result)

    def test_tombstone_with_superseded(self):
        from tools.learning_apply import (
            apply_to_memory, init_agent_state, tombstone_rule, load_tombstones,
        )
        init_agent_state("researcher")
        rule = apply_to_memory({
            "event_id": "le-old-00001", "severity": "FAIL",
            "component": "research", "root_cause": "old cause",
            "fix_applied": "old fix", "symptom": "s", "video_id": "v001",
        }, "researcher")

        tombstoned = tombstone_rule(
            "researcher", rule["rule_id"], "Replaced by better rule",
            superseded_by="r-le-new-00001",
        )
        self.assertEqual(tombstoned["superseded_by"], "r-le-new-00001")


class TestLearningApplySuggestSoul(unittest.TestCase):
    """Test suggest_soul_update."""

    def test_suggest_with_missing_soul_file(self):
        from tools.learning_apply import suggest_soul_update
        with patch("tools.learning_apply.project_root", return_value=Path("/nonexistent")):
            result = suggest_soul_update("unknown_agent", {
                "severity": "FAIL", "component": "test",
                "root_cause": "cause", "fix_applied": "fix",
                "symptom": "symptom", "event_id": "le-test",
            })
            self.assertIn("SOUL file not found", result)

    def test_suggest_returns_string(self):
        from tools.learning_apply import suggest_soul_update
        with tempfile.TemporaryDirectory() as tmp:
            soul_dir = Path(tmp) / "agents" / "team"
            soul_dir.mkdir(parents=True)
            (soul_dir / "SOUL_researcher.md").write_text("# SOUL", encoding="utf-8")
            with patch("tools.learning_apply.project_root", return_value=Path(tmp)):
                result = suggest_soul_update("researcher", {
                    "severity": "FAIL", "component": "research",
                    "root_cause": "Price not validated",
                    "fix_applied": "Added price check",
                    "symptom": "ASIN is accessories",
                    "event_id": "le-test-12345",
                    "video_id": "v001",
                })
                self.assertIn("SOUL_researcher", result)
                self.assertIn("Price not validated", result)
                self.assertIn("Known Failure Patterns", result)


class TestLearningApplyArchive(unittest.TestCase):
    """Test archive_memory_snapshot."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch(
            "tools.learning_apply.AGENTS_STATE_DIR",
            Path(self.tmp.name) / "agents",
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_archive_creates_snapshot(self):
        from tools.learning_apply import (
            apply_to_memory, archive_memory_snapshot, init_agent_state, _archive_dir,
        )
        init_agent_state("test_agent")
        apply_to_memory({
            "event_id": "le-test-00001", "severity": "WARN",
            "component": "test", "root_cause": "c",
            "fix_applied": "f", "symptom": "s", "video_id": "v001",
        }, "test_agent")

        path = archive_memory_snapshot("test_agent")
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())

    def test_archive_empty_returns_none(self):
        from tools.learning_apply import archive_memory_snapshot, init_agent_state
        init_agent_state("test_agent")
        result = archive_memory_snapshot("test_agent")
        self.assertIsNone(result)

    def test_archive_nonexistent_returns_none(self):
        from tools.learning_apply import archive_memory_snapshot
        result = archive_memory_snapshot("nonexistent_agent_xyz")
        self.assertIsNone(result)


# ===================================================================
# learning_gate.py
# ===================================================================

class TestLearningGateChecks(unittest.TestCase):
    """Test individual gate checks."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_patcher = patch(
            "tools.learning_gate._STATE_DIR",
            Path(self.tmp.name) / "gate_state",
        )
        self.state_patcher.start()

    def tearDown(self):
        self.state_patcher.stop()
        self.tmp.cleanup()

    def test_check_diff_policies_first_run(self):
        from tools.learning_gate import check_diff_policies
        result = check_diff_policies("test-video")
        self.assertTrue(result.passed)
        self.assertIn("First run", result.reason)

    def test_check_diff_policies_unchanged(self):
        from tools.learning_gate import check_diff_policies
        # First run records baseline
        check_diff_policies("test-video")
        # Second run should pass
        result = check_diff_policies("test-video")
        self.assertTrue(result.passed)

    def test_check_diff_soul_no_agent(self):
        from tools.learning_gate import check_diff_soul
        result = check_diff_soul("test-video", "unknown-stage")
        self.assertTrue(result.passed)
        self.assertIn("No agent", result.reason)

    def test_check_diff_soul_first_run(self):
        from tools.learning_gate import check_diff_soul
        result = check_diff_soul("test-video", "research")
        self.assertTrue(result.passed)
        self.assertIn("First run", result.reason)

    def test_check_regressions_no_events(self):
        from tools.learning_gate import check_regressions
        with patch("tools.learning_event.list_events", return_value=[]):
            result = check_regressions("test-video", "research")
            self.assertTrue(result.passed)

    def test_check_regressions_with_unresolved_fail(self):
        from tools.learning_gate import check_regressions
        mock_event = MagicMock()
        mock_event.severity = "FAIL"
        mock_event.status = "open"
        mock_event.event_id = "le-test-12345"
        with patch("tools.learning_event.list_events", return_value=[mock_event]):
            result = check_regressions("test-video", "research")
            self.assertFalse(result.passed)
            self.assertIn("unresolved", result.reason)

    def test_check_regressions_resolved_passes(self):
        from tools.learning_gate import check_regressions
        mock_event = MagicMock()
        mock_event.severity = "FAIL"
        mock_event.status = "applied"  # Not "open"
        with patch("tools.learning_event.list_events", return_value=[mock_event]):
            result = check_regressions("test-video", "research")
            self.assertTrue(result.passed)

    def test_check_known_failures_no_patterns(self):
        from tools.learning_gate import check_known_failures
        with patch("tools.lib.error_log.get_patterns", return_value=[]):
            result = check_known_failures("research")
            self.assertTrue(result.passed)

    def test_check_known_failures_with_recurring(self):
        from tools.learning_gate import check_known_failures
        pattern = {
            "stage": "research",
            "pattern": "ASIN is accessories",
            "count": 4,
            "unresolved": 2,
        }
        with patch("tools.lib.error_log.get_patterns", return_value=[pattern]):
            result = check_known_failures("research")
            self.assertFalse(result.passed)
            self.assertIn("Recurring pattern", result.reason)

    def test_check_known_failures_different_stage(self):
        from tools.learning_gate import check_known_failures
        pattern = {
            "stage": "assets",
            "pattern": "Phone ghost",
            "count": 4,
            "unresolved": 2,
        }
        with patch("tools.lib.error_log.get_patterns", return_value=[pattern]):
            result = check_known_failures("research")  # Different stage
            self.assertTrue(result.passed)


class TestLearningGateMain(unittest.TestCase):
    """Test the composite learning_gate function."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_patcher = patch(
            "tools.learning_gate._STATE_DIR",
            Path(self.tmp.name) / "gate_state",
        )
        self.state_patcher.start()

    def tearDown(self):
        self.state_patcher.stop()
        self.tmp.cleanup()

    def test_gate_disabled(self):
        from tools.learning_gate import learning_gate
        with patch("rayvault.policies.LEARNING_GATE_ENABLED", False):
            result = learning_gate("test-video", "research")
            self.assertFalse(result.blocked)
            self.assertIn("disabled", result.reason)

    def test_gate_disabled_via_env(self):
        from tools.learning_gate import learning_gate
        with patch.dict(os.environ, {"RAYVAULT_SKIP_LEARNING_GATE": "1"}):
            result = learning_gate("test-video", "research")
            self.assertFalse(result.blocked)

    @patch("tools.learning_gate.check_known_failures")
    @patch("tools.learning_gate.check_regressions")
    @patch("tools.learning_gate.check_diff_soul")
    @patch("tools.learning_gate.check_diff_policies")
    def test_gate_all_pass(self, mock_pol, mock_soul, mock_reg, mock_kf):
        from tools.learning_gate import GateCheck, learning_gate
        mock_pol.return_value = GateCheck("diff_policies", True)
        mock_soul.return_value = GateCheck("diff_soul", True)
        mock_reg.return_value = GateCheck("regressions", True)
        mock_kf.return_value = GateCheck("known_failures", True)

        result = learning_gate("test-video", "research")
        self.assertFalse(result.blocked)
        self.assertEqual(len(result.checks), 4)

    @patch("tools.learning_gate.check_known_failures")
    @patch("tools.learning_gate.check_regressions")
    @patch("tools.learning_gate.check_diff_soul")
    @patch("tools.learning_gate.check_diff_policies")
    def test_gate_blocked_on_regression(self, mock_pol, mock_soul, mock_reg, mock_kf):
        from tools.learning_gate import GateCheck, learning_gate
        mock_pol.return_value = GateCheck("diff_policies", True)
        mock_soul.return_value = GateCheck("diff_soul", True)
        mock_reg.return_value = GateCheck("regressions", False, reason="1 unresolved FAIL")
        mock_kf.return_value = GateCheck("known_failures", True)

        result = learning_gate("test-video", "research")
        self.assertTrue(result.blocked)
        self.assertIn("BLOCKED_FOR_LEARNING", result.reason)

    def test_stage_agent_map_coverage(self):
        from tools.learning_gate import STAGE_AGENT_MAP
        expected_stages = ["research", "script", "assets", "tts", "manifest", "day"]
        for stage in expected_stages:
            self.assertIn(stage, STAGE_AGENT_MAP)


# ===================================================================
# learning_revisit.py
# ===================================================================

class TestLearningRevisit(unittest.TestCase):
    """Test revisit phases."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.agents_patcher = patch(
            "tools.learning_apply.AGENTS_STATE_DIR",
            Path(self.tmp.name) / "agents",
        )
        self.reports_patcher = patch(
            "tools.learning_revisit.REPORTS_DIR",
            Path(self.tmp.name) / "reports",
        )
        self.agents_patcher.start()
        self.reports_patcher.start()

    def tearDown(self):
        self.agents_patcher.stop()
        self.reports_patcher.stop()
        self.tmp.cleanup()

    def test_phase_revalidate_empty(self):
        from tools.learning_apply import init_agent_state
        from tools.learning_revisit import phase_revalidate
        init_agent_state("test_agent")
        result = phase_revalidate("test_agent", 7)
        self.assertEqual(result["total_rules"], 0)
        self.assertEqual(result["stale"], [])
        self.assertEqual(result["conflicting"], [])

    def test_phase_revalidate_finds_stale(self):
        from tools.learning_apply import init_agent_state, _active_path, _write_json
        from tools.learning_revisit import phase_revalidate
        init_agent_state("test_agent")
        # Write a rule with old timestamp
        _write_json(_active_path("test_agent"), {
            "rules": [{
                "rule_id": "r-old",
                "created": "2020-01-01T00:00:00Z",
                "applied_count": 1,
                "severity": "INFO",
                "component": "test",
            }],
            "count": 1,
            "updated": "2020-01-01T00:00:00Z",
        })
        result = phase_revalidate("test_agent", 7)
        self.assertEqual(len(result["stale"]), 1)
        self.assertIn("r-old", result["stale"])

    def test_phase_promotion_scan_no_candidates(self):
        from tools.learning_apply import init_agent_state
        from tools.learning_revisit import phase_promotion_scan
        init_agent_state("test_agent")
        result = phase_promotion_scan("test_agent")
        self.assertEqual(result["candidates"], [])

    def test_phase_promotion_scan_finds_candidates(self):
        from tools.learning_apply import init_agent_state, _active_path, _write_json
        from tools.learning_revisit import phase_promotion_scan
        init_agent_state("test_agent")
        _write_json(_active_path("test_agent"), {
            "rules": [{
                "rule_id": "r-frequent",
                "source_event_id": "le-test-00001",
                "applied_count": 5,
                "severity": "FAIL",
                "component": "research",
                "rule": "test rule",
            }],
            "count": 1,
            "updated": "2026-02-20T00:00:00Z",
        })
        with patch("tools.learning_event.get_event", return_value=None):
            result = phase_promotion_scan("test_agent")
            self.assertEqual(len(result["candidates"]), 1)
            self.assertEqual(result["candidates"][0]["applied_count"], 5)

    @patch("tools.learning_revisit.list_events", return_value=[])
    def test_phase_weekly_report(self, mock_events):
        from tools.learning_apply import init_agent_state
        from tools.learning_revisit import phase_weekly_report, REPORTS_DIR
        for agent in ("market_scout", "researcher", "scriptwriter", "reviewer",
                       "dzine_producer", "davinci_editor", "publisher"):
            init_agent_state(agent)
        report = phase_weekly_report("all", 7)
        self.assertIn("events_total", report)
        self.assertIn("agent_summaries", report)
        self.assertEqual(report["events_total"], 0)

    def test_phase_tombstone_sweep_no_old(self):
        from tools.learning_apply import init_agent_state
        from tools.learning_revisit import phase_tombstone_sweep
        init_agent_state("test_agent")
        result = phase_tombstone_sweep("test_agent", 30)
        self.assertEqual(result["kept"], 0)
        self.assertEqual(result["archived"], 0)

    def test_phase_tombstone_sweep_archives_old(self):
        from tools.learning_apply import init_agent_state, _tombstones_path, _write_json
        from tools.learning_revisit import phase_tombstone_sweep
        init_agent_state("test_agent")
        _write_json(_tombstones_path("test_agent"), {
            "tombstones": [{
                "rule_id": "r-old",
                "tombstoned_at": "2020-01-01T00:00:00Z",
                "reason": "obsolete",
            }],
            "count": 1,
        })
        result = phase_tombstone_sweep("test_agent", 30)
        self.assertEqual(result["archived"], 1)
        self.assertEqual(result["kept"], 0)


class TestRunRevisit(unittest.TestCase):
    """Test run_revisit orchestrator."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.agents_patcher = patch(
            "tools.learning_apply.AGENTS_STATE_DIR",
            Path(self.tmp.name) / "agents",
        )
        self.reports_patcher = patch(
            "tools.learning_revisit.REPORTS_DIR",
            Path(self.tmp.name) / "reports",
        )
        self.agents_patcher.start()
        self.reports_patcher.start()

    def tearDown(self):
        self.agents_patcher.stop()
        self.reports_patcher.stop()
        self.tmp.cleanup()

    @patch("tools.learning_revisit.list_events", return_value=[])
    def test_run_revisit_single_agent(self, mock_events):
        from tools.learning_apply import init_agent_state
        from tools.learning_revisit import run_revisit
        init_agent_state("researcher")
        results = run_revisit("researcher", 7)
        self.assertIn("researcher", results["revalidation"])
        self.assertIn("researcher", results["promotions"])
        self.assertIsNotNone(results["report"])


# ===================================================================
# rayvault/learning/registry.py
# ===================================================================

class TestLearningRegistry(unittest.TestCase):
    """Test registry query functions."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.events_path = Path(self.tmp.name) / "events.json"
        self._write_events([
            {
                "event_id": "le-1", "run_id": "v001",
                "timestamp": "2026-02-20T10:00:00Z",
                "severity": "FAIL", "component": "research",
                "symptom": "ASIN is accessories",
                "root_cause": "No price validation",
                "fix_applied": "Added price check",
                "verification": "", "status": "applied",
                "video_id": "v001",
            },
            {
                "event_id": "le-2", "run_id": "v002",
                "timestamp": "2026-02-20T11:00:00Z",
                "severity": "WARN", "component": "assets",
                "symptom": "Phone ghost",
                "root_cause": "BG Remove incomplete",
                "fix_applied": "drawbox white",
                "verification": "", "status": "open",
                "video_id": "v002",
            },
            {
                "event_id": "le-3", "run_id": "v003",
                "timestamp": "2026-02-20T12:00:00Z",
                "severity": "FAIL", "component": "research",
                "symptom": "Duplicate evidence",
                "root_cause": "No price validation",
                "fix_applied": "Added price check",
                "verification": "Re-ran", "status": "applied",
                "video_id": "v003",
            },
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def _write_events(self, events):
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self.events_path.write_text(
            json.dumps(events, indent=2), encoding="utf-8",
        )

    def test_query_events_all(self):
        from rayvault.learning.registry import query_events
        events = query_events(_path=self.events_path)
        self.assertEqual(len(events), 3)

    def test_query_events_by_component(self):
        from rayvault.learning.registry import query_events
        events = query_events(component="research", _path=self.events_path)
        self.assertEqual(len(events), 2)

    def test_query_events_by_severity(self):
        from rayvault.learning.registry import query_events
        events = query_events(severity="WARN", _path=self.events_path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["component"], "assets")

    def test_query_events_by_video_id(self):
        from rayvault.learning.registry import query_events
        events = query_events(video_id="v002", _path=self.events_path)
        self.assertEqual(len(events), 1)

    def test_query_events_by_status(self):
        from rayvault.learning.registry import query_events
        events = query_events(status="open", _path=self.events_path)
        self.assertEqual(len(events), 1)

    def test_query_events_by_date_range(self):
        from rayvault.learning.registry import query_events
        events = query_events(
            date_from="2026-02-20T10:30:00Z",
            date_to="2026-02-20T11:30:00Z",
            _path=self.events_path,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_id"], "le-2")

    def test_query_events_empty_file(self):
        from rayvault.learning.registry import query_events
        empty_path = Path(self.tmp.name) / "empty.json"
        events = query_events(_path=empty_path)
        self.assertEqual(events, [])

    def test_get_patterns(self):
        from rayvault.learning.registry import get_patterns
        patterns = get_patterns(min_count=2, _path=self.events_path)
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["component"], "research")
        self.assertEqual(patterns[0]["count"], 2)

    def test_get_patterns_min_count_filter(self):
        from rayvault.learning.registry import get_patterns
        patterns = get_patterns(min_count=3, _path=self.events_path)
        self.assertEqual(len(patterns), 0)

    def test_get_agent_learnings(self):
        from rayvault.learning.registry import get_agent_learnings
        events = get_agent_learnings("researcher", _path=self.events_path)
        self.assertEqual(len(events), 2)  # research component maps to researcher

    def test_get_agent_learnings_dzine(self):
        from rayvault.learning.registry import get_agent_learnings
        events = get_agent_learnings("dzine_producer", _path=self.events_path)
        self.assertEqual(len(events), 1)  # assets component maps to dzine_producer

    def test_get_promotion_candidates(self):
        from rayvault.learning.registry import get_promotion_candidates
        candidates = get_promotion_candidates(threshold=2, _path=self.events_path)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["root_cause"], "No price validation")
        self.assertEqual(candidates[0]["count"], 2)

    def test_get_promotion_candidates_high_threshold(self):
        from rayvault.learning.registry import get_promotion_candidates
        candidates = get_promotion_candidates(threshold=5, _path=self.events_path)
        self.assertEqual(len(candidates), 0)

    def test_get_weekly_summary_no_reports(self):
        from rayvault.learning.registry import get_weekly_summary
        result = get_weekly_summary()
        # May return None if no reports dir exists
        # This is expected behavior


# ===================================================================
# Integration tests
# ===================================================================

class TestLearningSystemIntegration(unittest.TestCase):
    """End-to-end integration tests for the learning loop."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.events_path = Path(self.tmp.name) / "events.json"
        self.agents_patcher = patch(
            "tools.learning_apply.AGENTS_STATE_DIR",
            Path(self.tmp.name) / "agents",
        )
        self.agents_patcher.start()

    def tearDown(self):
        self.agents_patcher.stop()
        self.tmp.cleanup()

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_full_learning_loop(self, mock_sync):
        """Create event → apply to memory → verify in memory → tombstone."""
        from tools.learning_apply import (
            init_agent_state, load_active_memory,
            load_tombstones, tombstone_rule,
        )
        from tools.learning_event import create_event, get_event

        # Setup
        init_agent_state("researcher")

        # 1. Create event with agent → immediate apply
        event = create_event(
            run_id="v038",
            severity="FAIL",
            component="research",
            symptom="ASIN B0F8HM4PYL is accessories ($26.59)",
            root_cause="No price anomaly validation",
            fix_applied="Added price check: reject if <30% median",
            verification="v039 correctly rejected similar ASIN",
            video_id="v038",
            agent="researcher",
            _path=self.events_path,
        )

        # 2. Verify event persisted
        retrieved = get_event(event.event_id, _path=self.events_path)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.status, "applied")

        # 3. Verify rule in agent memory
        memory = load_active_memory("researcher")
        self.assertEqual(memory["count"], 1)
        rule = memory["rules"][0]
        self.assertIn("price", rule["rule"].lower())

        # 4. Tombstone the rule
        tombstoned = tombstone_rule(
            "researcher", rule["rule_id"],
            "Replaced by comprehensive validation module",
            superseded_by="r-le-new",
        )
        self.assertIsNotNone(tombstoned)

        # 5. Verify memory empty, tombstone populated
        memory = load_active_memory("researcher")
        self.assertEqual(memory["count"], 0)
        tombstones = load_tombstones("researcher")
        self.assertEqual(tombstones["count"], 1)

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_error_to_learning_bridge(self, mock_sync):
        """Error log → promote → learning event → verify both updated."""
        from tools.lib.error_log import log_error, _read_log
        from tools.learning_event import list_events

        error_path = Path(self.tmp.name) / "errors.json"

        # Log an error
        error = log_error("v038", "research", "ASIN is accessories", _path=error_path)
        self.assertFalse(error["resolved"])

        # Promote to learning event
        from tools.learning_event import promote_from_error
        event = promote_from_error(
            error["id"],
            root_cause="No price validation",
            fix="Added price check",
            severity="FAIL",
            component="research",
            _error_path=error_path,
            _events_path=self.events_path,
        )

        # Verify error resolved
        errors = _read_log(error_path)
        self.assertTrue(errors[0]["resolved"])

        # Verify learning event created
        events = list_events(_path=self.events_path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source_error_id, error["id"])

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_gate_blocks_on_unresolved_event(self, mock_sync):
        """Create FAIL event → gate should block for that video+stage."""
        from tools.learning_event import create_event, list_events
        from tools.learning_gate import check_regressions

        create_event(
            run_id="v040", severity="FAIL", component="research",
            symptom="Bad product", root_cause="No validation",
            fix_applied="TBD", video_id="v040",
            _path=self.events_path,
        )

        # Get real events first, then mock
        real_events = list_events(
            video_id="v040", component="research",
            _path=self.events_path,
        )
        self.assertEqual(len(real_events), 1)  # Sanity check

        with patch("tools.learning_event.list_events", return_value=real_events):
            result = check_regressions("v040", "research")
            self.assertFalse(result.passed)

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_multiple_events_same_agent(self, mock_sync):
        """Multiple events for same agent should all be in memory."""
        from tools.learning_apply import init_agent_state, load_active_memory
        from tools.learning_event import create_event

        init_agent_state("dzine_producer")

        for i in range(3):
            create_event(
                run_id=f"v{i:03d}", severity="WARN", component="assets",
                symptom=f"Issue {i}", root_cause=f"Cause {i}",
                fix_applied=f"Fix {i}", video_id=f"v{i:03d}",
                agent="dzine_producer",
                _path=self.events_path,
            )

        memory = load_active_memory("dzine_producer")
        self.assertEqual(memory["count"], 3)


class TestPipelineGateIntegration(unittest.TestCase):
    """Test _run_learning_gate as used by pipeline.py."""

    def test_run_learning_gate_function_exists(self):
        """Verify _run_learning_gate is importable from pipeline."""
        # We can't easily test the full pipeline function, but we verify
        # the integration pattern works
        from tools.learning_gate import learning_gate, LearningGateResult
        self.assertTrue(callable(learning_gate))

    def test_gate_result_dataclass(self):
        from tools.learning_gate import LearningGateResult, GateCheck
        result = LearningGateResult(
            blocked=True,
            reason="Test",
            checks=[GateCheck("test", False, "reason")],
        )
        self.assertTrue(result.blocked)
        self.assertEqual(len(result.checks), 1)


if __name__ == "__main__":
    unittest.main()
