"""Tests for tools/learning_gate.py — pipeline gate checks.

Covers: learning_gate, check_diff_policies, check_diff_soul,
        check_regressions, check_known_failures, GateCheck,
        LearningGateResult, STAGE_AGENT_MAP, disabled gate path.
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

from tools.learning_gate import (
    GateCheck,
    LearningGateResult,
    STAGE_AGENT_MAP,
    check_diff_policies,
    check_diff_soul,
    check_known_failures,
    check_regressions,
    learning_gate,
    _sha1_of_file,
    _STATE_DIR,
)


class TestGateCheckModel(unittest.TestCase):
    """Tests for GateCheck and LearningGateResult dataclasses."""

    def test_gate_check_pass(self):
        gc = GateCheck(name="test", passed=True)
        self.assertTrue(gc.passed)
        self.assertEqual(gc.reason, "")

    def test_gate_check_fail(self):
        gc = GateCheck(name="test", passed=False, reason="Something wrong")
        self.assertFalse(gc.passed)
        self.assertEqual(gc.reason, "Something wrong")

    def test_learning_gate_result_not_blocked(self):
        r = LearningGateResult(blocked=False, reason="All passed")
        self.assertFalse(r.blocked)
        self.assertEqual(r.checks, [])

    def test_learning_gate_result_blocked(self):
        r = LearningGateResult(
            blocked=True,
            reason="BLOCKED",
            checks=[GateCheck(name="c1", passed=False, reason="fail")],
        )
        self.assertTrue(r.blocked)
        self.assertEqual(len(r.checks), 1)


class TestStageAgentMap(unittest.TestCase):
    """Tests for STAGE_AGENT_MAP coverage."""

    def test_all_stages_mapped(self):
        expected = {"research", "script", "script-brief", "script-review",
                    "assets", "tts", "manifest", "render", "publish", "day"}
        self.assertEqual(set(STAGE_AGENT_MAP.keys()), expected)

    def test_known_mappings(self):
        self.assertEqual(STAGE_AGENT_MAP["research"], "researcher")
        self.assertEqual(STAGE_AGENT_MAP["assets"], "dzine_producer")
        self.assertEqual(STAGE_AGENT_MAP["manifest"], "davinci_editor")
        self.assertEqual(STAGE_AGENT_MAP["tts"], "publisher")


class TestSha1OfFile(unittest.TestCase):
    """Tests for _sha1_of_file helper."""

    def test_existing_file(self):
        tmp = Path(tempfile.mktemp())
        tmp.write_text("hello world")
        sha = _sha1_of_file(tmp)
        self.assertEqual(len(sha), 40)
        tmp.unlink()

    def test_nonexistent_file(self):
        sha = _sha1_of_file(Path("/tmp/does_not_exist_12345.py"))
        self.assertEqual(sha, "")

    def test_deterministic(self):
        tmp = Path(tempfile.mktemp())
        tmp.write_text("consistent content")
        a = _sha1_of_file(tmp)
        b = _sha1_of_file(tmp)
        self.assertEqual(a, b)
        tmp.unlink()


class TestCheckDiffPolicies(unittest.TestCase):
    """Tests for check_diff_policies."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Redirect state dir
        import tools.learning_gate as mod
        self._mod = mod
        self._orig_state_dir = mod._STATE_DIR
        mod._STATE_DIR = Path(self.tmpdir) / "gate_state"

    def tearDown(self):
        self._mod._STATE_DIR = self._orig_state_dir

    def test_first_run_passes(self):
        gc = check_diff_policies("v001")
        self.assertTrue(gc.passed)
        self.assertIn("First run", gc.reason)

    def test_unchanged_passes(self):
        check_diff_policies("v001")  # First run
        gc = check_diff_policies("v001")  # Second run
        self.assertTrue(gc.passed)

    def test_changed_fails(self):
        check_diff_policies("v001")
        # Simulate policies.py change by modifying state
        state_path = Path(self.tmpdir) / "gate_state" / "v001.json"
        state = json.loads(state_path.read_text())
        state["policies_sha"] = "0000000000000000000000000000000000000000"
        state_path.write_text(json.dumps(state))
        gc = check_diff_policies("v001")
        self.assertFalse(gc.passed)
        self.assertIn("changed", gc.reason)


class TestCheckDiffSoul(unittest.TestCase):
    """Tests for check_diff_soul."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import tools.learning_gate as mod
        self._mod = mod
        self._orig_state_dir = mod._STATE_DIR
        mod._STATE_DIR = Path(self.tmpdir) / "gate_state"

    def tearDown(self):
        self._mod._STATE_DIR = self._orig_state_dir

    def test_unmapped_stage_passes(self):
        gc = check_diff_soul("v001", "unknown_stage")
        self.assertTrue(gc.passed)
        self.assertIn("No agent mapped", gc.reason)

    def test_first_run_passes(self):
        gc = check_diff_soul("v001", "research")
        self.assertTrue(gc.passed)
        self.assertIn("First run", gc.reason)

    def test_unchanged_passes(self):
        check_diff_soul("v001", "research")
        gc = check_diff_soul("v001", "research")
        self.assertTrue(gc.passed)

    def test_changed_fails(self):
        check_diff_soul("v001", "research")
        state_path = Path(self.tmpdir) / "gate_state" / "v001.json"
        state = json.loads(state_path.read_text())
        state["soul_shas"]["researcher"] = "0000000000000000000000000000000000000000"
        state_path.write_text(json.dumps(state))
        gc = check_diff_soul("v001", "research")
        self.assertFalse(gc.passed)
        self.assertIn("changed", gc.reason)


class TestCheckRegressions(unittest.TestCase):
    """Tests for check_regressions."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.events_path = Path(self.tmpdir) / "learning_events.json"

    @patch("tools.learning_event.list_events")
    def test_no_events_passes(self, mock_list):
        mock_list.return_value = []
        gc = check_regressions("v001", "research")
        self.assertTrue(gc.passed)

    @patch("tools.learning_event.list_events")
    def test_unresolved_fail_blocks(self, mock_list):
        from tools.learning_event import LearningEvent
        mock_list.return_value = [
            LearningEvent(
                event_id="le-test-00001", run_id="run001",
                timestamp="2026-02-19T12:00:00Z", severity="FAIL",
                component="research", symptom="test", root_cause="c",
                fix_applied="f", verification="", status="open",
                video_id="v001",
            ),
        ]
        gc = check_regressions("v001", "research")
        self.assertFalse(gc.passed)
        self.assertIn("unresolved", gc.reason)

    @patch("tools.learning_event.list_events")
    def test_resolved_fail_passes(self, mock_list):
        from tools.learning_event import LearningEvent
        mock_list.return_value = [
            LearningEvent(
                event_id="le-test-00001", run_id="run001",
                timestamp="2026-02-19T12:00:00Z", severity="FAIL",
                component="research", symptom="test", root_cause="c",
                fix_applied="f", verification="v", status="applied",
                video_id="v001",
            ),
        ]
        gc = check_regressions("v001", "research")
        self.assertTrue(gc.passed)

    @patch("tools.learning_event.list_events")
    def test_info_events_pass(self, mock_list):
        from tools.learning_event import LearningEvent
        mock_list.return_value = [
            LearningEvent(
                event_id="le-test-00001", run_id="run001",
                timestamp="2026-02-19T12:00:00Z", severity="INFO",
                component="research", symptom="test", root_cause="c",
                fix_applied="f", verification="", status="open",
                video_id="v001",
            ),
        ]
        gc = check_regressions("v001", "research")
        self.assertTrue(gc.passed)


class TestCheckKnownFailures(unittest.TestCase):
    """Tests for check_known_failures."""

    @patch("tools.lib.error_log.get_patterns")
    def test_no_patterns_passes(self, mock_patterns):
        mock_patterns.return_value = []
        gc = check_known_failures("research")
        self.assertTrue(gc.passed)

    @patch("tools.lib.error_log.get_patterns")
    def test_matching_pattern_blocks(self, mock_patterns):
        mock_patterns.return_value = [
            {"stage": "research", "pattern": "ASIN not found", "count": 5, "unresolved": 3},
        ]
        gc = check_known_failures("research")
        self.assertFalse(gc.passed)
        self.assertIn("Recurring pattern", gc.reason)

    @patch("tools.lib.error_log.get_patterns")
    def test_resolved_pattern_passes(self, mock_patterns):
        mock_patterns.return_value = [
            {"stage": "research", "pattern": "ASIN not found", "count": 5, "unresolved": 0},
        ]
        gc = check_known_failures("research")
        self.assertTrue(gc.passed)

    @patch("tools.lib.error_log.get_patterns")
    def test_different_stage_passes(self, mock_patterns):
        mock_patterns.return_value = [
            {"stage": "assets", "pattern": "Image fail", "count": 5, "unresolved": 3},
        ]
        gc = check_known_failures("research")
        self.assertTrue(gc.passed)


class TestLearningGate(unittest.TestCase):
    """Tests for learning_gate() main function."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import tools.learning_gate as mod
        self._mod = mod
        self._orig_state_dir = mod._STATE_DIR
        mod._STATE_DIR = Path(self.tmpdir) / "gate_state"

    def tearDown(self):
        self._mod._STATE_DIR = self._orig_state_dir

    @patch("tools.learning_gate.check_known_failures")
    @patch("tools.learning_gate.check_regressions")
    def test_all_pass(self, mock_reg, mock_kf):
        mock_reg.return_value = GateCheck(name="regressions", passed=True)
        mock_kf.return_value = GateCheck(name="known_failures", passed=True)
        result = learning_gate("v001", "research")
        self.assertFalse(result.blocked)
        self.assertEqual(len(result.checks), 4)

    @patch("tools.learning_gate.check_known_failures")
    @patch("tools.learning_gate.check_regressions")
    def test_regression_blocks(self, mock_reg, mock_kf):
        mock_reg.return_value = GateCheck(
            name="regressions", passed=False, reason="Unresolved FAIL",
        )
        mock_kf.return_value = GateCheck(name="known_failures", passed=True)
        result = learning_gate("v001", "research")
        self.assertTrue(result.blocked)
        self.assertIn("BLOCKED_FOR_LEARNING", result.reason)

    @patch("rayvault.policies.LEARNING_GATE_ENABLED", False)
    @patch("tools.learning_gate.check_known_failures")
    @patch("tools.learning_gate.check_regressions")
    def test_disabled_gate_passes(self, mock_reg, mock_kf):
        result = learning_gate("v001", "research")
        self.assertFalse(result.blocked)
        self.assertIn("disabled", result.reason)
        mock_reg.assert_not_called()
        mock_kf.assert_not_called()

    @patch.dict("os.environ", {"RAYVAULT_SKIP_LEARNING_GATE": "1"})
    @patch("tools.learning_gate.check_known_failures")
    @patch("tools.learning_gate.check_regressions")
    def test_env_skip_passes(self, mock_reg, mock_kf):
        result = learning_gate("v001", "research")
        self.assertFalse(result.blocked)
        mock_reg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
