"""Tests for tools/lib/error_log.py and pipeline errors subcommand.

Covers: log_error, resolve_error, get_unresolved, get_patterns,
        format_log_text, cmd_errors integration.
No external deps — stdlib only.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.error_log import (
    ERROR_LOG_PATH,
    format_log_text,
    get_lessons,
    get_patterns,
    get_stale,
    get_unresolved,
    log_error,
    resolve_error,
)


class TestLogError(unittest.TestCase):
    """Tests for log_error()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "error_log.json"

    def test_log_error_creates_file(self):
        entry = log_error("v001", "research", "Test error", _path=self.log_path)
        self.assertTrue(self.log_path.is_file())
        data = json.loads(self.log_path.read_text())
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["video_id"], "v001")
        self.assertEqual(data[0]["stage"], "research")
        self.assertEqual(data[0]["error"], "Test error")
        self.assertFalse(data[0]["resolved"])
        self.assertIsNone(data[0]["resolution"])
        self.assertTrue(entry["id"].startswith("e-"))

    def test_log_error_appends(self):
        log_error("v001", "research", "Error 1", _path=self.log_path)
        log_error("v002", "script", "Error 2", _path=self.log_path)
        data = json.loads(self.log_path.read_text())
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["video_id"], "v001")
        self.assertEqual(data[1]["video_id"], "v002")

    def test_log_error_unique_ids(self):
        e1 = log_error("v001", "research", "Error A", _path=self.log_path)
        e2 = log_error("v001", "research", "Error B", _path=self.log_path)
        self.assertNotEqual(e1["id"], e2["id"])

    def test_log_error_with_context(self):
        ctx = {"command": "research", "mode": "build"}
        entry = log_error("v001", "research", "Fail", context=ctx,
                          _path=self.log_path)
        self.assertEqual(entry["context"], ctx)
        data = json.loads(self.log_path.read_text())
        self.assertEqual(data[0]["context"]["command"], "research")

    def test_log_error_exit_code(self):
        entry = log_error("v001", "research", "Action needed", exit_code=2,
                          _path=self.log_path)
        self.assertEqual(entry["exit_code"], 2)
        data = json.loads(self.log_path.read_text())
        self.assertEqual(data[0]["exit_code"], 2)

    def test_log_error_default_exit_code(self):
        entry = log_error("v001", "research", "Fail", _path=self.log_path)
        self.assertEqual(entry["exit_code"], 1)


class TestResolveError(unittest.TestCase):
    """Tests for resolve_error()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "error_log.json"

    def test_resolve_error(self):
        entry = log_error("v001", "research", "Bad data", _path=self.log_path)
        result = resolve_error(entry["id"], "Missing source", "Added fallback",
                               _path=self.log_path)
        self.assertIsNotNone(result)
        self.assertTrue(result["resolved"])
        self.assertEqual(result["resolution"]["root_cause"], "Missing source")
        self.assertEqual(result["resolution"]["fix"], "Added fallback")
        self.assertIn("resolved_at", result["resolution"])
        # Verify persisted
        data = json.loads(self.log_path.read_text())
        self.assertTrue(data[0]["resolved"])

    def test_resolve_unknown_id(self):
        log_error("v001", "research", "Error", _path=self.log_path)
        result = resolve_error("e-nonexistent-00000", "?", "?",
                               _path=self.log_path)
        self.assertIsNone(result)


class TestGetUnresolved(unittest.TestCase):
    """Tests for get_unresolved()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "error_log.json"

    def test_get_unresolved(self):
        e1 = log_error("v001", "research", "Err 1", _path=self.log_path)
        log_error("v002", "script", "Err 2", _path=self.log_path)
        resolve_error(e1["id"], "fixed", "patched", _path=self.log_path)
        unresolved = get_unresolved(_path=self.log_path)
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["video_id"], "v002")

    def test_get_unresolved_filter_stage(self):
        log_error("v001", "research", "Err 1", _path=self.log_path)
        log_error("v002", "script", "Err 2", _path=self.log_path)
        result = get_unresolved(stage="research", _path=self.log_path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["stage"], "research")

    def test_get_unresolved_filter_video(self):
        log_error("v001", "research", "Err 1", _path=self.log_path)
        log_error("v002", "research", "Err 2", _path=self.log_path)
        result = get_unresolved(video_id="v002", _path=self.log_path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["video_id"], "v002")


class TestGetPatterns(unittest.TestCase):
    """Tests for get_patterns()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "error_log.json"

    def test_get_patterns(self):
        log_error("v001", "research", "Empty shortlist", _path=self.log_path)
        log_error("v002", "research", "Empty shortlist", _path=self.log_path)
        log_error("v003", "script", "Unique error", _path=self.log_path)
        patterns = get_patterns(_path=self.log_path)
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["stage"], "research")
        self.assertEqual(patterns[0]["pattern"], "Empty shortlist")
        self.assertEqual(patterns[0]["count"], 2)
        self.assertIn("v001", patterns[0]["video_ids"])
        self.assertIn("v002", patterns[0]["video_ids"])

    def test_get_patterns_min_count(self):
        log_error("v001", "research", "Err A", _path=self.log_path)
        log_error("v002", "research", "Err A", _path=self.log_path)
        log_error("v003", "research", "Err A", _path=self.log_path)
        # min_count=3 should still return the pattern
        patterns = get_patterns(min_count=3, _path=self.log_path)
        self.assertEqual(len(patterns), 1)
        # min_count=4 should filter it out
        patterns = get_patterns(min_count=4, _path=self.log_path)
        self.assertEqual(len(patterns), 0)

    def test_get_patterns_groups_by_truncated_error(self):
        long_err = "x" * 100
        log_error("v001", "research", long_err, _path=self.log_path)
        log_error("v002", "research", long_err, _path=self.log_path)
        patterns = get_patterns(_path=self.log_path)
        self.assertEqual(len(patterns), 1)
        # Pattern should be truncated to 80 chars
        self.assertEqual(len(patterns[0]["pattern"]), 80)


class TestFormatLogText(unittest.TestCase):
    """Tests for format_log_text()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "error_log.json"

    def test_format_log_text_empty(self):
        text = format_log_text(_path=self.log_path)
        self.assertEqual(text, "No errors found.")

    def test_format_log_text_with_entries(self):
        log_error("v001", "research", "Empty shortlist", _path=self.log_path)
        text = format_log_text(_path=self.log_path)
        self.assertIn("v001", text)
        self.assertIn("research", text)
        self.assertIn("Empty shortlist", text)
        self.assertIn("OPEN", text)

    def test_format_log_excludes_resolved(self):
        e = log_error("v001", "research", "Fixed error", _path=self.log_path)
        resolve_error(e["id"], "root", "fix", _path=self.log_path)
        text = format_log_text(_path=self.log_path)
        self.assertEqual(text, "No errors found.")

    def test_format_log_includes_resolved(self):
        e = log_error("v001", "research", "Fixed error", _path=self.log_path)
        resolve_error(e["id"], "root", "fix applied", _path=self.log_path)
        text = format_log_text(show_resolved=True, _path=self.log_path)
        self.assertIn("RESOLVED", text)
        self.assertIn("fix applied", text)

    def test_format_log_limit(self):
        for i in range(30):
            log_error(f"v{i:03d}", "research", f"Error {i}",
                      _path=self.log_path)
        text = format_log_text(limit=5, _path=self.log_path)
        # Should show most recent 5 (v029..v025), not all 30
        self.assertIn("v029", text)
        self.assertNotIn("v000", text)


class TestCorruptAndMissing(unittest.TestCase):
    """Tests for resilience to corrupt/missing files."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "error_log.json"

    def test_corrupt_file_handled(self):
        self.log_path.write_text("not valid json{{{", encoding="utf-8")
        # Should not crash, starts fresh
        entry = log_error("v001", "research", "After corrupt",
                          _path=self.log_path)
        self.assertEqual(entry["video_id"], "v001")
        data = json.loads(self.log_path.read_text())
        self.assertEqual(len(data), 1)

    def test_missing_dir_created(self):
        deep_path = Path(self.tmpdir) / "a" / "b" / "error_log.json"
        entry = log_error("v001", "research", "Deep path",
                          _path=deep_path)
        self.assertTrue(deep_path.is_file())
        self.assertEqual(entry["video_id"], "v001")


class TestGetLessons(unittest.TestCase):
    """Tests for get_lessons()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "error_log.json"

    def test_get_lessons_empty(self):
        lessons = get_lessons(_path=self.log_path)
        self.assertEqual(lessons, [])

    def test_get_lessons_from_resolved(self):
        e1 = log_error("v001", "research", "Empty shortlist", _path=self.log_path)
        resolve_error(e1["id"], "Niche too narrow", "Widen niche keyword",
                      _path=self.log_path)
        e2 = log_error("v002", "research", "Empty shortlist", _path=self.log_path)
        resolve_error(e2["id"], "Niche too narrow", "Widen niche keyword",
                      _path=self.log_path)

        lessons = get_lessons(_path=self.log_path)
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]["stage"], "research")
        self.assertEqual(lessons[0]["pattern"], "Empty shortlist")
        self.assertEqual(lessons[0]["occurrences"], 2)
        self.assertEqual(lessons[0]["root_cause"], "Niche too narrow")
        self.assertEqual(lessons[0]["fix"], "Widen niche keyword")
        self.assertIn("last_resolved", lessons[0])


class TestGetStale(unittest.TestCase):
    """Tests for get_stale()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "error_log.json"

    def test_get_stale_empty(self):
        # Fresh error (just created) should not be stale
        log_error("v001", "research", "Recent error", _path=self.log_path)
        stale = get_stale(days=7, _path=self.log_path)
        self.assertEqual(stale, [])

    def test_get_stale_finds_old(self):
        # Inject an error with a very old timestamp
        old_entry = {
            "id": "e-old-12345",
            "video_id": "v001",
            "timestamp": "2020-01-01T00:00:00+00:00",
            "stage": "research",
            "exit_code": 1,
            "error": "Ancient error",
            "context": {},
            "resolved": False,
            "resolution": None,
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(json.dumps([old_entry]), encoding="utf-8")

        stale = get_stale(days=7, _path=self.log_path)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["id"], "e-old-12345")


class TestCmdErrors(unittest.TestCase):
    """Tests for cmd_errors() in pipeline.py."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "error_log.json"

    def _make_args(self, **kwargs):
        defaults = {
            "stage": "", "video_id": "", "all": False,
            "patterns": False, "resolve": "",
            "lessons": False, "stale": False,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_cmd_errors_empty(self):
        from tools.pipeline import cmd_errors
        args = self._make_args()
        with patch("tools.lib.error_log.ERROR_LOG_PATH", self.log_path), \
             patch("tools.pipeline._log_error") as mock_log:
            rc = cmd_errors(args)
        self.assertEqual(rc, 0)

    def test_cmd_errors_with_data(self):
        log_error("v001", "research", "Test error", _path=self.log_path)
        from tools.pipeline import cmd_errors
        args = self._make_args()
        with patch("tools.lib.error_log.ERROR_LOG_PATH", self.log_path):
            rc = cmd_errors(args)
        self.assertEqual(rc, 0)

    def test_cmd_errors_patterns(self):
        log_error("v001", "research", "Same error", _path=self.log_path)
        log_error("v002", "research", "Same error", _path=self.log_path)
        from tools.pipeline import cmd_errors
        args = self._make_args(patterns=True)
        with patch("tools.lib.error_log.ERROR_LOG_PATH", self.log_path):
            rc = cmd_errors(args)
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
