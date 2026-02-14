"""Tests for tools/lib/run_log.py and pipeline runs subcommand.

Covers: log_run, get_runs, format_runs_text, get_daily_summary, cmd_runs.
No external deps -- stdlib only.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.run_log import (
    RUN_LOG_PATH,
    format_runs_text,
    get_daily_summary,
    get_runs,
    log_run,
)


class TestLogRun(unittest.TestCase):
    """Tests for log_run()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "run_log.json"

    def test_log_run_creates_file(self):
        entry = log_run("v001", "research", 0, 142.3, _path=self.log_path)
        self.assertTrue(self.log_path.is_file())
        data = json.loads(self.log_path.read_text())
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["video_id"], "v001")

    def test_log_run_appends(self):
        log_run("v001", "research", 0, 100.0, _path=self.log_path)
        log_run("v002", "script", 0, 50.0, _path=self.log_path)
        data = json.loads(self.log_path.read_text())
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["video_id"], "v001")
        self.assertEqual(data[1]["video_id"], "v002")

    def test_log_run_fields(self):
        entry = log_run("v042", "research", 0, 142.3, niche="portable speakers",
                         _path=self.log_path)
        self.assertEqual(entry["video_id"], "v042")
        self.assertEqual(entry["command"], "research")
        self.assertEqual(entry["exit_code"], 0)
        self.assertEqual(entry["duration_s"], 142.3)
        self.assertEqual(entry["niche"], "portable speakers")
        self.assertIn("timestamp", entry)


class TestGetRuns(unittest.TestCase):
    """Tests for get_runs()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "run_log.json"
        # Seed some entries
        log_run("v001", "research", 0, 100.0, _path=self.log_path)
        log_run("v001", "script", 0, 50.0, _path=self.log_path)
        log_run("v002", "research", 1, 30.0, _path=self.log_path)

    def test_get_runs_unfiltered(self):
        runs = get_runs(_path=self.log_path)
        self.assertEqual(len(runs), 3)

    def test_get_runs_filter_video(self):
        runs = get_runs(video_id="v001", _path=self.log_path)
        self.assertEqual(len(runs), 2)
        for r in runs:
            self.assertEqual(r["video_id"], "v001")

    def test_get_runs_filter_command(self):
        runs = get_runs(command="research", _path=self.log_path)
        self.assertEqual(len(runs), 2)
        for r in runs:
            self.assertEqual(r["command"], "research")

    def test_get_runs_filter_since(self):
        # All entries have timestamps from now, so "since yesterday" returns all
        runs = get_runs(since="2000-01-01", _path=self.log_path)
        self.assertEqual(len(runs), 3)
        # "since far future" returns none
        runs = get_runs(since="2099-01-01", _path=self.log_path)
        self.assertEqual(len(runs), 0)

    def test_get_runs_limit(self):
        runs = get_runs(limit=2, _path=self.log_path)
        self.assertEqual(len(runs), 2)
        # Should return the last 2 entries
        self.assertEqual(runs[0]["command"], "script")
        self.assertEqual(runs[1]["command"], "research")


class TestFormatRunsText(unittest.TestCase):
    """Tests for format_runs_text()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "run_log.json"

    def test_format_runs_text_empty(self):
        text = format_runs_text(_path=self.log_path)
        self.assertEqual(text, "No runs recorded.")

    def test_format_runs_text(self):
        log_run("v001", "research", 0, 142.3, niche="speakers", _path=self.log_path)
        log_run("v001", "script", 1, 5.2, _path=self.log_path)
        text = format_runs_text(_path=self.log_path)
        self.assertIn("v001", text)
        self.assertIn("research", text)
        self.assertIn("142.3", text)
        self.assertIn("OK", text)
        self.assertIn("EXIT 1", text)


class TestDailySummary(unittest.TestCase):
    """Tests for get_daily_summary()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "run_log.json"

    def test_daily_summary(self):
        log_run("v001", "research", 0, 100.0, _path=self.log_path)
        log_run("v001", "script", 0, 50.0, _path=self.log_path)
        log_run("v002", "research", 1, 30.0, _path=self.log_path)

        # All entries are from today
        summary = get_daily_summary(_path=self.log_path)
        self.assertEqual(summary["total_runs"], 3)
        self.assertIn("research", summary["by_command"])
        self.assertEqual(summary["by_command"]["research"]["count"], 2)
        self.assertEqual(summary["by_command"]["research"]["ok"], 1)
        self.assertEqual(summary["by_command"]["research"]["failed"], 1)
        self.assertEqual(summary["by_command"]["research"]["avg_duration_s"], 65.0)
        self.assertIn("v001", summary["videos_touched"])
        self.assertIn("v002", summary["videos_touched"])

    def test_daily_summary_empty(self):
        summary = get_daily_summary(date="1999-01-01", _path=self.log_path)
        self.assertEqual(summary["total_runs"], 0)
        self.assertEqual(summary["by_command"], {})
        self.assertEqual(summary["videos_touched"], [])


class TestCorruptFile(unittest.TestCase):
    """Tests for resilience to corrupt/missing files."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "run_log.json"

    def test_corrupt_file_handled(self):
        self.log_path.write_text("not valid json{{{", encoding="utf-8")
        entry = log_run("v001", "research", 0, 10.0, _path=self.log_path)
        self.assertEqual(entry["video_id"], "v001")
        data = json.loads(self.log_path.read_text())
        self.assertEqual(len(data), 1)


class TestCmdRuns(unittest.TestCase):
    """Tests for cmd_runs() in pipeline.py."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "run_log.json"

    def _make_args(self, **kwargs):
        defaults = {
            "video_id": "", "filter_command": "",
            "today": False, "summary": False,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_cmd_runs_empty(self):
        from tools.pipeline import cmd_runs
        args = self._make_args()
        with patch("tools.lib.run_log.RUN_LOG_PATH", self.log_path):
            rc = cmd_runs(args)
        self.assertEqual(rc, 0)

    def test_cmd_runs_summary(self):
        log_run("v001", "research", 0, 100.0, _path=self.log_path)
        from tools.pipeline import cmd_runs
        args = self._make_args(summary=True)
        with patch("tools.lib.run_log.RUN_LOG_PATH", self.log_path):
            rc = cmd_runs(args)
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
