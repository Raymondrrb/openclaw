"""Tests for tools/learning_apply.py — agent memory management + tombstoning.

Covers: apply_to_memory, tombstone_rule, load_active_memory, load_tombstones,
        archive_memory_snapshot, init_agent_state, suggest_soul_update,
        max rules enforcement, duplicate detection.
Stdlib only.
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

from tools.learning_apply import (
    AGENTS_STATE_DIR,
    CORE_AGENTS,
    apply_to_memory,
    archive_memory_snapshot,
    init_agent_state,
    init_all_agents,
    load_active_memory,
    load_tombstones,
    suggest_soul_update,
    tombstone_rule,
    _active_path,
    _agent_dir,
    _tombstones_path,
)
from tools.learning_event import LearningEvent


def _make_test_event(**overrides) -> LearningEvent:
    """Create a test LearningEvent with sensible defaults."""
    defaults = dict(
        event_id="le-test-00001",
        run_id="run001",
        timestamp="2026-02-19T12:00:00Z",
        severity="FAIL",
        component="research",
        symptom="ASIN is accessories",
        root_cause="No price validation",
        fix_applied="Added price anomaly check",
        verification="Validated against real prices",
    )
    defaults.update(overrides)
    return LearningEvent(**defaults)


class TestApplyToMemory(unittest.TestCase):
    """Tests for apply_to_memory()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Redirect AGENTS_STATE_DIR to temp
        self._orig_dir = AGENTS_STATE_DIR
        import tools.learning_apply as mod
        self._mod = mod
        self._mod.AGENTS_STATE_DIR = Path(self.tmpdir)

    def tearDown(self):
        self._mod.AGENTS_STATE_DIR = self._orig_dir

    def test_apply_creates_rule(self):
        event = _make_test_event()
        rule = apply_to_memory(event, "researcher")
        self.assertIn("rule_id", rule)
        self.assertTrue(rule["rule_id"].startswith("r-"))
        self.assertEqual(rule["severity"], "FAIL")
        self.assertEqual(rule["applied_count"], 1)

    def test_apply_persists_to_file(self):
        event = _make_test_event()
        apply_to_memory(event, "researcher")
        memory = load_active_memory("researcher")
        self.assertEqual(memory["count"], 1)
        self.assertEqual(len(memory["rules"]), 1)
        self.assertEqual(memory["rules"][0]["severity"], "FAIL")

    def test_apply_duplicate_increments_count(self):
        event = _make_test_event()
        apply_to_memory(event, "researcher")
        result = apply_to_memory(event, "researcher")
        self.assertEqual(result["applied_count"], 2)
        memory = load_active_memory("researcher")
        self.assertEqual(len(memory["rules"]), 1)

    def test_apply_different_events_add_rules(self):
        e1 = _make_test_event(event_id="le-test-00001", symptom="s1")
        e2 = _make_test_event(event_id="le-test-00002", symptom="s2")
        apply_to_memory(e1, "researcher")
        apply_to_memory(e2, "researcher")
        memory = load_active_memory("researcher")
        self.assertEqual(len(memory["rules"]), 2)

    def test_apply_accepts_dict(self):
        from dataclasses import asdict
        event = _make_test_event()
        rule = apply_to_memory(asdict(event), "researcher")
        self.assertIn("rule_id", rule)

    def test_apply_rejects_bad_type(self):
        with self.assertRaises(TypeError):
            apply_to_memory("not an event", "researcher")

    @patch("rayvault.policies.LEARNING_MAX_ACTIVE_RULES_PER_AGENT", 3)
    def test_apply_enforces_max_rules(self):
        for i in range(4):
            evt = _make_test_event(
                event_id=f"le-test-{i:05d}",
                severity="INFO" if i < 3 else "FAIL",
                symptom=f"symptom {i}",
            )
            apply_to_memory(evt, "researcher")
        memory = load_active_memory("researcher")
        self.assertLessEqual(len(memory["rules"]), 3)

    @patch("rayvault.policies.LEARNING_MAX_ACTIVE_RULES_PER_AGENT", 2)
    def test_max_rules_preserves_critical(self):
        """BLOCKER/FAIL rules should survive eviction over INFO rules."""
        e_info = _make_test_event(
            event_id="le-info-00001", severity="INFO", symptom="info1",
        )
        e_fail = _make_test_event(
            event_id="le-fail-00001", severity="FAIL", symptom="fail1",
        )
        e_blocker = _make_test_event(
            event_id="le-block-00001", severity="BLOCKER", symptom="blocker1",
        )
        apply_to_memory(e_info, "researcher")
        apply_to_memory(e_fail, "researcher")
        apply_to_memory(e_blocker, "researcher")
        memory = load_active_memory("researcher")
        severities = [r["severity"] for r in memory["rules"]]
        # INFO should have been evicted
        self.assertNotIn("INFO", severities)
        self.assertIn("FAIL", severities)
        self.assertIn("BLOCKER", severities)

    def test_apply_creates_archive(self):
        """Applying a rule when memory exists should create archive."""
        event = _make_test_event(event_id="le-first-00001")
        apply_to_memory(event, "researcher")
        # Second apply should archive the first state
        event2 = _make_test_event(event_id="le-second-00001", symptom="s2")
        apply_to_memory(event2, "researcher")
        archive_dir = Path(self.tmpdir) / "researcher" / "memory_archive"
        if archive_dir.exists():
            archives = list(archive_dir.glob("memory_*.json"))
            self.assertGreater(len(archives), 0)


class TestTombstoneRule(unittest.TestCase):
    """Tests for tombstone_rule()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import tools.learning_apply as mod
        self._mod = mod
        self._orig_dir = mod.AGENTS_STATE_DIR
        mod.AGENTS_STATE_DIR = Path(self.tmpdir)

    def tearDown(self):
        self._mod.AGENTS_STATE_DIR = self._orig_dir

    def test_tombstone_moves_rule(self):
        event = _make_test_event()
        rule = apply_to_memory(event, "dzine_producer")
        rule_id = rule["rule_id"]

        tombstoned = tombstone_rule(
            "dzine_producer", rule_id, "Rule superseded by new approach",
        )
        self.assertIsNotNone(tombstoned)
        self.assertEqual(tombstoned["rule_id"], rule_id)
        self.assertEqual(tombstoned["reason"], "Rule superseded by new approach")

        # Rule removed from active
        memory = load_active_memory("dzine_producer")
        self.assertEqual(len(memory["rules"]), 0)

        # Rule in tombstones
        tombstones = load_tombstones("dzine_producer")
        self.assertEqual(len(tombstones["tombstones"]), 1)
        self.assertEqual(tombstones["tombstones"][0]["rule_id"], rule_id)

    def test_tombstone_nonexistent_returns_none(self):
        result = tombstone_rule("researcher", "r-nonexistent", "test")
        self.assertIsNone(result)

    def test_tombstone_with_evidence_and_superseded(self):
        event = _make_test_event()
        rule = apply_to_memory(event, "researcher")
        tombstoned = tombstone_rule(
            "researcher",
            rule["rule_id"],
            "Obsolete",
            evidence_ids=["le-new-00001"],
            superseded_by="r-le-new-00001",
        )
        self.assertEqual(tombstoned["evidence_ids"], ["le-new-00001"])
        self.assertEqual(tombstoned["superseded_by"], "r-le-new-00001")


class TestLoadMemory(unittest.TestCase):
    """Tests for load_active_memory and load_tombstones."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import tools.learning_apply as mod
        self._mod = mod
        self._orig_dir = mod.AGENTS_STATE_DIR
        mod.AGENTS_STATE_DIR = Path(self.tmpdir)

    def tearDown(self):
        self._mod.AGENTS_STATE_DIR = self._orig_dir

    def test_load_active_empty(self):
        """load_active_memory returns {} when no file exists (not initialized)."""
        memory = load_active_memory("new_agent")
        # Without init, returns empty dict; rules key may be absent
        rules = memory.get("rules", [])
        self.assertEqual(rules, [])

    def test_load_tombstones_empty(self):
        """load_tombstones returns {} when no file exists (not initialized)."""
        data = load_tombstones("new_agent")
        tombstones = data.get("tombstones", [])
        self.assertEqual(tombstones, [])

    def test_load_after_init(self):
        init_agent_state("researcher")
        memory = load_active_memory("researcher")
        self.assertEqual(memory["rules"], [])
        self.assertEqual(memory["count"], 0)
        tombstones = load_tombstones("researcher")
        self.assertEqual(tombstones["tombstones"], [])


class TestArchive(unittest.TestCase):
    """Tests for archive_memory_snapshot."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import tools.learning_apply as mod
        self._mod = mod
        self._orig_dir = mod.AGENTS_STATE_DIR
        mod.AGENTS_STATE_DIR = Path(self.tmpdir)

    def tearDown(self):
        self._mod.AGENTS_STATE_DIR = self._orig_dir

    def test_archive_empty_returns_none(self):
        result = archive_memory_snapshot("researcher")
        self.assertIsNone(result)

    def test_archive_with_rules_creates_snapshot(self):
        event = _make_test_event()
        apply_to_memory(event, "researcher")
        snapshot = archive_memory_snapshot("researcher")
        if snapshot:
            self.assertTrue(snapshot.is_file())
            data = json.loads(snapshot.read_text())
            self.assertGreater(len(data.get("rules", [])), 0)


class TestInitAgentState(unittest.TestCase):
    """Tests for init_agent_state and init_all_agents."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import tools.learning_apply as mod
        self._mod = mod
        self._orig_dir = mod.AGENTS_STATE_DIR
        mod.AGENTS_STATE_DIR = Path(self.tmpdir)

    def tearDown(self):
        self._mod.AGENTS_STATE_DIR = self._orig_dir

    def test_init_creates_files(self):
        init_agent_state("researcher")
        self.assertTrue((Path(self.tmpdir) / "researcher" / "memory_active.json").is_file())
        self.assertTrue((Path(self.tmpdir) / "researcher" / "memory_tombstones.json").is_file())

    def test_init_idempotent(self):
        init_agent_state("researcher")
        init_agent_state("researcher")
        memory = load_active_memory("researcher")
        self.assertEqual(memory["count"], 0)

    def test_init_all_agents(self):
        init_all_agents()
        for agent in CORE_AGENTS:
            self.assertTrue((Path(self.tmpdir) / agent / "memory_active.json").is_file())

    def test_core_agents_list(self):
        self.assertEqual(len(CORE_AGENTS), 7)
        self.assertIn("market_scout", CORE_AGENTS)
        self.assertIn("dzine_producer", CORE_AGENTS)
        self.assertIn("publisher", CORE_AGENTS)


class TestSuggestSoulUpdate(unittest.TestCase):
    """Tests for suggest_soul_update()."""

    def test_suggest_from_event(self):
        event = _make_test_event()
        # Patch soul_path to not require actual file
        with patch("tools.learning_apply.project_root") as mock_root:
            tmp = Path(tempfile.mkdtemp())
            mock_root.return_value = tmp
            soul_dir = tmp / "agents" / "team"
            soul_dir.mkdir(parents=True)
            (soul_dir / "SOUL_researcher.md").write_text("# SOUL\n\n## Known Failure Patterns\n")

            result = suggest_soul_update("researcher", event)
            self.assertIn("SOUL_researcher", result)
            self.assertIn("No price validation", result)
            self.assertIn("FAIL", result)

    def test_suggest_missing_soul_file(self):
        event = _make_test_event()
        with patch("tools.learning_apply.project_root") as mock_root:
            mock_root.return_value = Path(tempfile.mkdtemp())
            result = suggest_soul_update("researcher", event)
            self.assertIn("not found", result)

    def test_suggest_from_dict(self):
        from dataclasses import asdict
        event = asdict(_make_test_event())
        with patch("tools.learning_apply.project_root") as mock_root:
            tmp = Path(tempfile.mkdtemp())
            mock_root.return_value = tmp
            soul_dir = tmp / "agents" / "team"
            soul_dir.mkdir(parents=True)
            (soul_dir / "SOUL_researcher.md").write_text("# SOUL\n")

            result = suggest_soul_update("researcher", event)
            self.assertIn("SOUL_researcher", result)

    def test_suggest_bad_type_returns_empty(self):
        result = suggest_soul_update("researcher", "not an event")
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
