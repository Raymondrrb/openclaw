"""Tests for tools/migrate_errors_to_learning.py — batch migration script.

Covers: _migrate_resolved_errors, _migrate_skill_graph_learnings,
        idempotency, dry-run mode, section extraction.
Stdlib only.
"""

from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.migrate_errors_to_learning import (
    _extract_sections,
    _migrate_resolved_errors,
    _migrate_skill_graph_learnings,
    _SEVERITY_MAP,
)


class TestExtractSections(unittest.TestCase):
    """Tests for _extract_sections markdown parser."""

    def test_basic_sections(self):
        text = textwrap.dedent("""\
        # Title

        ## Symptom
        Something broke

        ## Root Cause
        Bad input

        ## Fix Applied
        Fixed the input
        """)
        sections = _extract_sections(text)
        self.assertEqual(sections["symptom"], "Something broke")
        self.assertEqual(sections["root cause"], "Bad input")
        self.assertEqual(sections["fix applied"], "Fixed the input")

    def test_multiline_sections(self):
        text = textwrap.dedent("""\
        ## Incident
        Line one
        Line two
        Line three

        ## Fix
        The fix
        """)
        sections = _extract_sections(text)
        self.assertIn("Line one", sections["incident"])
        self.assertIn("Line three", sections["incident"])

    def test_empty_text(self):
        sections = _extract_sections("")
        self.assertEqual(sections, {})

    def test_no_sections(self):
        sections = _extract_sections("Just plain text\nwithout headers")
        self.assertEqual(sections, {})


class TestSeverityMap(unittest.TestCase):
    """Tests for severity mapping."""

    def test_all_expected_mappings(self):
        self.assertEqual(_SEVERITY_MAP["critical"], "BLOCKER")
        self.assertEqual(_SEVERITY_MAP["blocker"], "BLOCKER")
        self.assertEqual(_SEVERITY_MAP["high"], "FAIL")
        self.assertEqual(_SEVERITY_MAP["fail"], "FAIL")
        self.assertEqual(_SEVERITY_MAP["medium"], "WARN")
        self.assertEqual(_SEVERITY_MAP["warn"], "WARN")
        self.assertEqual(_SEVERITY_MAP["low"], "INFO")
        self.assertEqual(_SEVERITY_MAP["info"], "INFO")


class TestMigrateResolvedErrors(unittest.TestCase):
    """Tests for _migrate_resolved_errors."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    @patch("tools.migrate_errors_to_learning.list_events")
    @patch("tools.migrate_errors_to_learning._read_log")
    def test_no_resolved_errors(self, mock_read, mock_list):
        mock_read.return_value = [
            {"id": "e-1", "resolved": False, "resolution": None},
        ]
        mock_list.return_value = []
        count = _migrate_resolved_errors(dry_run=True, verbose=False)
        self.assertEqual(count, 0)

    @patch("tools.migrate_errors_to_learning.list_events")
    @patch("tools.migrate_errors_to_learning._read_log")
    def test_dry_run_counts(self, mock_read, mock_list):
        mock_read.return_value = [
            {
                "id": "e-1", "video_id": "v001", "stage": "research",
                "error": "Test error", "resolved": True,
                "resolution": {"root_cause": "bad input", "fix": "fixed it"},
            },
        ]
        mock_list.return_value = []
        count = _migrate_resolved_errors(dry_run=True, verbose=False)
        self.assertEqual(count, 1)

    @patch("tools.migrate_errors_to_learning.list_events")
    @patch("tools.migrate_errors_to_learning._read_log")
    def test_skips_already_migrated(self, mock_read, mock_list):
        from tools.learning_event import LearningEvent
        mock_read.return_value = [
            {
                "id": "e-1", "video_id": "v001", "stage": "research",
                "error": "Test error", "resolved": True,
                "resolution": {"root_cause": "bad", "fix": "fixed"},
            },
        ]
        mock_list.return_value = [
            LearningEvent(
                event_id="le-1", run_id="r1", timestamp="2026-02-19T12:00:00Z",
                severity="FAIL", component="research", symptom="test",
                root_cause="bad", fix_applied="fixed", verification="",
                source_error_id="e-1",
            ),
        ]
        count = _migrate_resolved_errors(dry_run=True, verbose=False)
        self.assertEqual(count, 0)


class TestMigrateSkillGraphLearnings(unittest.TestCase):
    """Tests for _migrate_skill_graph_learnings."""

    @patch("tools.migrate_errors_to_learning.list_events")
    @patch("tools.migrate_errors_to_learning.project_root")
    def test_dry_run_finds_manual_nodes(self, mock_root, mock_list):
        mock_list.return_value = []
        tmp = Path(tempfile.mkdtemp())
        mock_root.return_value = tmp
        learnings_dir = tmp / "agents" / "skills" / "learnings"
        learnings_dir.mkdir(parents=True)

        # Create a manual learning node
        (learnings_dir / "2026-02-19-test.md").write_text(textwrap.dedent("""\
        ---
        description: Test learning
        tags: [learning, dzine]
        severity: high
        fix: Applied the fix
        ---

        # Test Learning

        ## Incident
        Something happened

        ## Root Cause
        Bad config

        ## Fix Applied
        Fixed the config
        """))

        count = _migrate_skill_graph_learnings(dry_run=True, verbose=True)
        self.assertEqual(count, 1)

    @patch("tools.migrate_errors_to_learning.list_events")
    @patch("tools.migrate_errors_to_learning.project_root")
    def test_skips_learning_event_tagged(self, mock_root, mock_list):
        mock_list.return_value = []
        tmp = Path(tempfile.mkdtemp())
        mock_root.return_value = tmp
        learnings_dir = tmp / "agents" / "skills" / "learnings"
        learnings_dir.mkdir(parents=True)

        (learnings_dir / "2026-02-19-auto.md").write_text(textwrap.dedent("""\
        ---
        description: Auto-generated
        tags: [learning, learning-event, fail]
        severity: fail
        fix: auto fix
        ---

        # Auto Learning
        """))

        count = _migrate_skill_graph_learnings(dry_run=True, verbose=True)
        self.assertEqual(count, 0)

    @patch("tools.migrate_errors_to_learning.list_events")
    @patch("tools.migrate_errors_to_learning.project_root")
    def test_skips_no_severity(self, mock_root, mock_list):
        mock_list.return_value = []
        tmp = Path(tempfile.mkdtemp())
        mock_root.return_value = tmp
        learnings_dir = tmp / "agents" / "skills" / "learnings"
        learnings_dir.mkdir(parents=True)

        (learnings_dir / "2026-02-19-plain.md").write_text(textwrap.dedent("""\
        ---
        description: Just notes
        tags: [learning]
        ---

        # Notes
        """))

        count = _migrate_skill_graph_learnings(dry_run=True, verbose=True)
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
