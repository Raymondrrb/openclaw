"""Tests for tools/learning_event.py — learning event CRUD + immediate loop.

Covers: create_event, get_event, list_events, update_event,
        promote_from_error, sync_to_skill_graph, severity validation,
        per-video writes, _make_event_id uniqueness.
Stdlib only.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.learning_event import (
    SEVERITIES,
    STATUSES,
    LearningEvent,
    _make_event_id,
    create_event,
    get_event,
    list_events,
    update_event,
    promote_from_error,
    sync_to_skill_graph,
    _read_events,
)


class TestMakeEventId(unittest.TestCase):
    """Tests for _make_event_id uniqueness and format."""

    def test_format_starts_with_le(self):
        eid = _make_event_id("2026-02-19T12:00:00Z", "test symptom")
        self.assertTrue(eid.startswith("le-"))

    def test_different_symptoms_different_ids(self):
        a = _make_event_id("2026-02-19T12:00:00Z", "symptom A")
        b = _make_event_id("2026-02-19T12:00:00Z", "symptom B")
        self.assertNotEqual(a, b)

    def test_different_timestamps_different_ids(self):
        a = _make_event_id("2026-02-19T12:00:00Z", "same")
        b = _make_event_id("2026-02-19T12:00:01Z", "same")
        self.assertNotEqual(a, b)

    def test_deterministic(self):
        a = _make_event_id("2026-02-19T12:00:00Z", "same")
        b = _make_event_id("2026-02-19T12:00:00Z", "same")
        self.assertEqual(a, b)


class TestCreateEvent(unittest.TestCase):
    """Tests for create_event() CRUD lifecycle."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.events_path = Path(self.tmpdir) / "learning_events.json"

    def test_create_basic(self):
        evt = create_event(
            run_id="run001",
            severity="FAIL",
            component="research",
            symptom="ASIN is accessories",
            root_cause="No price validation",
            fix_applied="Added price anomaly check",
            _path=self.events_path,
        )
        self.assertIsInstance(evt, LearningEvent)
        self.assertTrue(evt.event_id.startswith("le-"))
        self.assertEqual(evt.severity, "FAIL")
        self.assertEqual(evt.component, "research")
        self.assertEqual(evt.status, "open")
        self.assertTrue(self.events_path.is_file())

    def test_create_persists_to_file(self):
        create_event(
            run_id="run001",
            severity="WARN",
            component="dzine",
            symptom="Phone ghost in BG Remove",
            root_cause="Ref had phone",
            fix_applied="Used drawbox to blank phone area",
            _path=self.events_path,
        )
        data = json.loads(self.events_path.read_text())
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["severity"], "WARN")

    def test_create_multiple_appends(self):
        for i in range(3):
            create_event(
                run_id=f"run{i:03d}",
                severity="INFO",
                component="research",
                symptom=f"Symptom {i}",
                root_cause="cause",
                fix_applied="fix",
                _path=self.events_path,
            )
        data = json.loads(self.events_path.read_text())
        self.assertEqual(len(data), 3)

    def test_create_invalid_severity_raises(self):
        with self.assertRaises(ValueError) as ctx:
            create_event(
                run_id="run001",
                severity="CRITICAL",
                component="research",
                symptom="test",
                root_cause="cause",
                fix_applied="fix",
                _path=self.events_path,
            )
        self.assertIn("CRITICAL", str(ctx.exception))

    def test_create_with_video_id(self):
        evt = create_event(
            run_id="run001",
            severity="FAIL",
            component="assets",
            symptom="Image hallucination",
            root_cause="Changed reference angle",
            fix_applied="Reverted to original angle",
            video_id="v038",
            _path=self.events_path,
        )
        self.assertEqual(evt.video_id, "v038")

    def test_create_with_source_error_id(self):
        evt = create_event(
            run_id="run001",
            severity="FAIL",
            component="research",
            symptom="test",
            root_cause="cause",
            fix_applied="fix",
            source_error_id="e-20260219T120000-abc12",
            _path=self.events_path,
        )
        self.assertEqual(evt.source_error_id, "e-20260219T120000-abc12")

    @patch("tools.learning_event.sync_to_skill_graph")
    @patch("tools.learning_apply.apply_to_memory")
    def test_create_with_agent_applies_to_memory(self, mock_apply, mock_sync):
        mock_apply.return_value = {"rule_id": "r-test"}
        evt = create_event(
            run_id="run001",
            severity="FAIL",
            component="assets",
            symptom="test symptom",
            root_cause="test cause",
            fix_applied="test fix",
            agent="dzine_producer",
            _path=self.events_path,
        )
        mock_apply.assert_called_once()
        self.assertEqual(evt.status, "applied")
        self.assertIn("test cause", evt.promotion_rule)

    @patch("tools.learning_event.sync_to_skill_graph")
    def test_create_calls_sync_to_skill_graph(self, mock_sync):
        create_event(
            run_id="run001",
            severity="INFO",
            component="research",
            symptom="test",
            root_cause="cause",
            fix_applied="fix",
            _path=self.events_path,
        )
        mock_sync.assert_called_once()


class TestGetEvent(unittest.TestCase):
    """Tests for get_event()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.events_path = Path(self.tmpdir) / "learning_events.json"

    def test_get_existing(self):
        evt = create_event(
            run_id="run001",
            severity="WARN",
            component="tts",
            symptom="Audio clipping",
            root_cause="Volume too high",
            fix_applied="Reduced volume by 3dB",
            _path=self.events_path,
        )
        found = get_event(evt.event_id, _path=self.events_path)
        self.assertIsNotNone(found)
        self.assertEqual(found.event_id, evt.event_id)
        self.assertEqual(found.severity, "WARN")

    def test_get_nonexistent(self):
        found = get_event("le-nonexistent-00000", _path=self.events_path)
        self.assertIsNone(found)

    def test_get_from_empty_file(self):
        found = get_event("le-nonexistent-00000", _path=self.events_path)
        self.assertIsNone(found)


class TestListEvents(unittest.TestCase):
    """Tests for list_events() filtering."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.events_path = Path(self.tmpdir) / "learning_events.json"
        # Create diverse events
        create_event(
            run_id="run001", severity="FAIL", component="research",
            symptom="s1", root_cause="c1", fix_applied="f1",
            video_id="v001", _path=self.events_path,
        )
        create_event(
            run_id="run002", severity="WARN", component="assets",
            symptom="s2", root_cause="c2", fix_applied="f2",
            video_id="v002", _path=self.events_path,
        )
        create_event(
            run_id="run003", severity="FAIL", component="assets",
            symptom="s3", root_cause="c3", fix_applied="f3",
            video_id="v001", _path=self.events_path,
        )

    def test_list_all(self):
        events = list_events(_path=self.events_path)
        self.assertEqual(len(events), 3)

    def test_filter_by_component(self):
        events = list_events(component="assets", _path=self.events_path)
        self.assertEqual(len(events), 2)

    def test_filter_by_severity(self):
        events = list_events(severity="FAIL", _path=self.events_path)
        self.assertEqual(len(events), 2)

    def test_filter_by_video_id(self):
        events = list_events(video_id="v001", _path=self.events_path)
        self.assertEqual(len(events), 2)

    def test_filter_combined(self):
        events = list_events(
            severity="FAIL", component="assets", _path=self.events_path,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].symptom, "s3")

    def test_filter_no_match(self):
        events = list_events(component="tts", _path=self.events_path)
        self.assertEqual(len(events), 0)

    def test_list_empty_file(self):
        empty_path = Path(self.tmpdir) / "empty.json"
        events = list_events(_path=empty_path)
        self.assertEqual(len(events), 0)


class TestUpdateEvent(unittest.TestCase):
    """Tests for update_event()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.events_path = Path(self.tmpdir) / "learning_events.json"
        self.evt = create_event(
            run_id="run001", severity="FAIL", component="research",
            symptom="test", root_cause="cause", fix_applied="fix",
            _path=self.events_path,
        )

    def test_update_status(self):
        updated = update_event(
            self.evt.event_id, status="verified", _path=self.events_path,
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, "verified")
        # Verify persisted
        found = get_event(self.evt.event_id, _path=self.events_path)
        self.assertEqual(found.status, "verified")

    def test_update_verification(self):
        updated = update_event(
            self.evt.event_id,
            verification="Ran tests, all pass",
            _path=self.events_path,
        )
        self.assertEqual(updated.verification, "Ran tests, all pass")

    def test_update_soul_update(self):
        updated = update_event(
            self.evt.event_id,
            soul_update="Add to known failures",
            _path=self.events_path,
        )
        self.assertEqual(updated.soul_update, "Add to known failures")

    def test_update_obsolete_rules(self):
        updated = update_event(
            self.evt.event_id,
            obsolete_rules_removed=["r-old-1", "r-old-2"],
            _path=self.events_path,
        )
        self.assertEqual(updated.obsolete_rules_removed, ["r-old-1", "r-old-2"])

    def test_update_invalid_status_raises(self):
        with self.assertRaises(ValueError):
            update_event(
                self.evt.event_id, status="invalid", _path=self.events_path,
            )

    def test_update_nonexistent_returns_none(self):
        result = update_event(
            "le-nonexistent-00000", status="verified", _path=self.events_path,
        )
        self.assertIsNone(result)


class TestPromoteFromError(unittest.TestCase):
    """Tests for promote_from_error() bridge."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.error_path = Path(self.tmpdir) / "error_log.json"
        self.events_path = Path(self.tmpdir) / "learning_events.json"

    def test_promote_creates_learning_event(self):
        from tools.lib.error_log import log_error
        entry = log_error("v038", "research", "ASIN is accessories",
                          _path=self.error_path)
        error_id = entry["id"]

        evt = promote_from_error(
            error_id,
            root_cause="No price validation",
            fix="Added price anomaly check",
            severity="FAIL",
            component="research",
            _error_path=self.error_path,
            _events_path=self.events_path,
        )
        self.assertIsNotNone(evt)
        self.assertEqual(evt.source_error_id, error_id)
        self.assertEqual(evt.severity, "FAIL")

        # Verify error is resolved
        from tools.lib.error_log import _read_log
        errors = _read_log(self.error_path)
        self.assertTrue(errors[0]["resolved"])

    def test_promote_nonexistent_error_returns_none(self):
        result = promote_from_error(
            "e-nonexistent-00000",
            root_cause="test",
            fix="test",
            _error_path=self.error_path,
            _events_path=self.events_path,
        )
        self.assertIsNone(result)


class TestSyncToSkillGraph(unittest.TestCase):
    """Tests for sync_to_skill_graph()."""

    @patch("tools.lib.skill_graph.record_learning")
    def test_sync_calls_record_learning(self, mock_record):
        mock_record.return_value = Path("/tmp/fake.md")
        evt = LearningEvent(
            event_id="le-test-00001",
            run_id="run001",
            timestamp="2026-02-19T12:00:00Z",
            severity="FAIL",
            component="dzine",
            symptom="Image hallucination in Product Background",
            root_cause="Changed reference angle from 3/4 to top-down",
            fix_applied="Reverted to original 3/4 angle",
            verification="Re-generated, product shape correct",
        )
        result = sync_to_skill_graph(evt)
        mock_record.assert_called_once()
        call_kwargs = mock_record.call_args
        self.assertIn("FAIL", call_kwargs.kwargs.get("title", ""))
        self.assertIn("learning-event", call_kwargs.kwargs.get("tags", []))

    @patch("tools.lib.skill_graph.record_learning")
    def test_sync_includes_component_tag(self, mock_record):
        mock_record.return_value = Path("/tmp/fake.md")
        evt = LearningEvent(
            event_id="le-test-00002",
            run_id="run002",
            timestamp="2026-02-19T12:00:00Z",
            severity="WARN",
            component="tts",
            symptom="Audio clipping",
            root_cause="Volume too high",
            fix_applied="Reduced volume",
            verification="",
        )
        sync_to_skill_graph(evt)
        tags = mock_record.call_args.kwargs.get("tags", [])
        self.assertIn("tts", tags)
        self.assertIn("warn", tags)


class TestLearningEventModel(unittest.TestCase):
    """Tests for LearningEvent dataclass."""

    def test_default_values(self):
        evt = LearningEvent(
            event_id="le-test",
            run_id="run001",
            timestamp="2026-02-19T12:00:00Z",
            severity="INFO",
            component="research",
            symptom="test",
            root_cause="cause",
            fix_applied="fix",
            verification="verified",
        )
        self.assertEqual(evt.status, "open")
        self.assertEqual(evt.video_id, "")
        self.assertEqual(evt.source_error_id, "")
        self.assertEqual(evt.promotion_rule, "")
        self.assertEqual(evt.soul_update, "")
        self.assertEqual(evt.obsolete_rules_removed, [])

    def test_asdict_roundtrip(self):
        evt = LearningEvent(
            event_id="le-test",
            run_id="run001",
            timestamp="2026-02-19T12:00:00Z",
            severity="BLOCKER",
            component="manifest",
            symptom="Render failed",
            root_cause="Missing media",
            fix_applied="Re-downloaded assets",
            verification="Render completed",
            video_id="v042",
        )
        d = asdict(evt)
        self.assertEqual(d["severity"], "BLOCKER")
        self.assertEqual(d["video_id"], "v042")

    def test_severities_constant(self):
        self.assertEqual(SEVERITIES, ("INFO", "WARN", "FAIL", "BLOCKER"))

    def test_statuses_constant(self):
        self.assertEqual(STATUSES, ("open", "applied", "verified", "archived"))


class TestReadEvents(unittest.TestCase):
    """Tests for _read_events edge cases."""

    def test_nonexistent_file(self):
        result = _read_events(Path("/tmp/nonexistent_events.json"))
        self.assertEqual(result, [])

    def test_corrupt_json(self):
        tmp = Path(tempfile.mktemp(suffix=".json"))
        tmp.write_text("not valid json {{{")
        result = _read_events(tmp)
        self.assertEqual(result, [])
        tmp.unlink(missing_ok=True)

    def test_non_list_json(self):
        tmp = Path(tempfile.mktemp(suffix=".json"))
        tmp.write_text('{"key": "value"}')
        result = _read_events(tmp)
        self.assertEqual(result, [])
        tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
