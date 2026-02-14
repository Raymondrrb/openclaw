"""Tests for tools.lib.job_worker — job execution worker."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_TEMP_DIR = tempfile.mkdtemp()

import tools.lib.job_system as js

js.JOBS_ROOT = Path(_TEMP_DIR) / "worker_tests"


class TestToolExecution(unittest.TestCase):
    """Test _execute_tool for each tool type."""

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"tools_{id(self)}"
        js.JOBS_ROOT = self.jobs_root
        self.job = js.create_job("Tool test", "Do stuff", admin_id=123)

    def test_write_file(self):
        from tools.lib.job_worker import _execute_tool

        result = _execute_tool(self.job, "write_file", {
            "filename": "test.md",
            "content": "# Hello\nWorld",
        })
        self.assertIn("Written", result)
        target = self.job.workspace / "test.md"
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_text(), "# Hello\nWorld")

    def test_write_file_nested(self):
        from tools.lib.job_worker import _execute_tool

        result = _execute_tool(self.job, "write_file", {
            "filename": "sub/dir/file.txt",
            "content": "nested",
        })
        self.assertIn("Written", result)
        self.assertTrue((self.job.workspace / "sub" / "dir" / "file.txt").is_file())

    def test_write_file_path_traversal(self):
        from tools.lib.job_worker import _execute_tool

        result = _execute_tool(self.job, "write_file", {
            "filename": "../../etc/passwd",
            "content": "hack",
        })
        self.assertIn("path traversal", result)

    def test_read_file(self):
        from tools.lib.job_worker import _execute_tool

        (self.job.workspace / "data.txt").write_text("Hello world")
        result = _execute_tool(self.job, "read_file", {"filename": "data.txt"})
        self.assertEqual(result, "Hello world")

    def test_read_file_not_found(self):
        from tools.lib.job_worker import _execute_tool

        result = _execute_tool(self.job, "read_file", {"filename": "nope.txt"})
        self.assertIn("not found", result)

    def test_read_file_path_traversal(self):
        from tools.lib.job_worker import _execute_tool

        result = _execute_tool(self.job, "read_file", {"filename": "../../../etc/passwd"})
        self.assertIn("path traversal", result)

    def test_read_file_truncation(self):
        from tools.lib.job_worker import _execute_tool

        big = "x" * 15000
        (self.job.workspace / "big.txt").write_text(big)
        result = _execute_tool(self.job, "read_file", {"filename": "big.txt"})
        self.assertIn("truncated", result)
        self.assertTrue(len(result) < 11000)

    def test_list_files(self):
        from tools.lib.job_worker import _execute_tool

        (self.job.workspace / "a.txt").write_text("a")
        (self.job.workspace / "b.txt").write_text("b")
        result = _execute_tool(self.job, "list_files", {"path": "."})
        self.assertIn("a.txt", result)
        self.assertIn("b.txt", result)

    def test_list_files_shows_dirs(self):
        from tools.lib.job_worker import _execute_tool

        (self.job.workspace / "subdir").mkdir()
        result = _execute_tool(self.job, "list_files", {"path": "."})
        self.assertIn("[DIR]", result)
        self.assertIn("subdir", result)

    def test_list_files_path_traversal(self):
        from tools.lib.job_worker import _execute_tool

        result = _execute_tool(self.job, "list_files", {"path": "../../../"})
        self.assertIn("path traversal", result)

    def test_add_source(self):
        from tools.lib.job_worker import _execute_tool

        result = _execute_tool(self.job, "add_source", {
            "url": "https://example.com",
            "title": "Example",
            "notes": "Good source",
            "reliability": "high",
        })
        self.assertIn("Source added", result)
        sources = json.loads((self.job.workspace / "sources.json").read_text())
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["title"], "Example")
        self.assertEqual(sources[0]["reliability"], "high")

    def test_add_multiple_sources(self):
        from tools.lib.job_worker import _execute_tool

        _execute_tool(self.job, "add_source", {"url": "https://a.com", "title": "A"})
        _execute_tool(self.job, "add_source", {"url": "https://b.com", "title": "B"})
        sources = json.loads((self.job.workspace / "sources.json").read_text())
        self.assertEqual(len(sources), 2)

    def test_update_checkpoint(self):
        from tools.lib.job_worker import _execute_tool

        js.start_job(self.job)
        result = _execute_tool(self.job, "update_checkpoint", {
            "summary": "Phase 1 done",
            "progress_percent": 33,
        })
        self.assertIn("Checkpoint updated", result)
        loaded = js.load_job(self.job.id)
        self.assertEqual(loaded.checkpoint, "Phase 1 done")
        self.assertEqual(loaded.progress_percent, 33)

    def test_request_permission(self):
        from tools.lib.job_worker import _execute_tool

        js.start_job(self.job)
        with patch("tools.lib.job_worker.send_telegram"):
            result = _execute_tool(self.job, "request_permission", {
                "action": "Install npm package",
                "reason": "Need express",
                "risk_level": "medium",
            })
        self.assertIn("Permission requested", result)
        self.assertEqual(self.job.status, "blocked")
        self.assertEqual(len(self.job.permissions), 1)

    def test_complete(self):
        from tools.lib.job_worker import _execute_tool

        js.start_job(self.job)
        (self.job.workspace / "output.md").write_text("# Final output")
        with patch("tools.lib.job_worker.send_telegram"):
            result = _execute_tool(self.job, "complete", {
                "summary": "All done",
            })
        self.assertIn("Job completed", result)
        self.assertEqual(self.job.status, "completed")
        self.assertEqual(len(self.job.artifacts), 1)
        self.assertEqual(self.job.artifacts[0].name, "output.md")

    def test_complete_no_output(self):
        from tools.lib.job_worker import _execute_tool

        js.start_job(self.job)
        with patch("tools.lib.job_worker.send_telegram"):
            result = _execute_tool(self.job, "complete", {"summary": "Done"})
        self.assertIn("Job completed", result)
        self.assertEqual(len(self.job.artifacts), 0)

    def test_unknown_tool(self):
        from tools.lib.job_worker import _execute_tool

        result = _execute_tool(self.job, "hack_the_planet", {})
        self.assertIn("Unknown tool", result)


class TestBuildSystemPrompt(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"prompt_{id(self)}"
        js.JOBS_ROOT = self.jobs_root

    def test_general_prompt(self):
        from tools.lib.job_worker import _build_system_prompt

        job = js.create_job("General", "Do stuff", admin_id=123, job_type="general")
        prompt = _build_system_prompt(job)
        self.assertIn("Rayviews Lab", prompt)
        self.assertNotIn("STUDY task", prompt)

    def test_study_prompt(self):
        from tools.lib.job_worker import _build_system_prompt

        job = js.create_job("Study", "Study X", admin_id=123, job_type="study")
        prompt = _build_system_prompt(job)
        self.assertIn("STUDY task", prompt)
        self.assertIn("Phase 1", prompt)
        self.assertIn("Phase 2", prompt)

    def test_instructions_included(self):
        from tools.lib.job_worker import _build_system_prompt

        job = js.create_job("Instr", "Do stuff", admin_id=123)
        job.instructions.append("Focus on X")
        job.instructions.append("Skip Y")
        prompt = _build_system_prompt(job)
        self.assertIn("Focus on X", prompt)
        self.assertIn("Skip Y", prompt)


class TestRunJob(unittest.TestCase):
    """Test run_job with mocked Anthropic API."""

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"run_{id(self)}"
        js.JOBS_ROOT = self.jobs_root

    @patch("tools.lib.job_worker._call_anthropic")
    @patch("tools.lib.job_worker.send_telegram")
    def test_simple_completion(self, mock_tg, mock_api):
        """Job that calls complete on first turn."""
        from tools.lib.job_worker import run_job

        job = js.create_job("Simple", "Do something simple", admin_id=123)

        # API returns tool_use for complete
        mock_api.return_value = {
            "content": [
                {"type": "text", "text": "I'll complete this now."},
                {
                    "type": "tool_use",
                    "id": "tu_1",
                    "name": "complete",
                    "input": {"summary": "Done with task"},
                },
            ],
            "stop_reason": "tool_use",
        }

        run_job(job.id)
        loaded = js.load_job(job.id)
        self.assertEqual(loaded.status, "completed")
        self.assertEqual(loaded.checkpoint, "Done with task")

    @patch("tools.lib.job_worker._call_anthropic")
    @patch("tools.lib.job_worker.send_telegram")
    def test_multi_turn(self, mock_tg, mock_api):
        """Job that writes a file, then completes."""
        from tools.lib.job_worker import run_job

        job = js.create_job("Multi", "Research and write", admin_id=123)

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "content": [
                        {"type": "tool_use", "id": "tu_1", "name": "write_file",
                         "input": {"filename": "output.md", "content": "# Research\nFindings here"}},
                    ],
                    "stop_reason": "tool_use",
                }
            return {
                "content": [
                    {"type": "tool_use", "id": "tu_2", "name": "complete",
                     "input": {"summary": "Research complete"}},
                ],
                "stop_reason": "tool_use",
            }

        mock_api.side_effect = side_effect

        run_job(job.id)
        loaded = js.load_job(job.id)
        self.assertEqual(loaded.status, "completed")
        self.assertTrue((loaded.workspace / "output.md").is_file())
        self.assertEqual(len(loaded.artifacts), 1)

    @patch("tools.lib.job_worker._call_anthropic")
    @patch("tools.lib.job_worker.send_telegram")
    def test_permission_blocks_job(self, mock_tg, mock_api):
        """Job that requests permission gets blocked."""
        from tools.lib.job_worker import run_job

        job = js.create_job("Perm", "Install something", admin_id=123)

        mock_api.return_value = {
            "content": [
                {"type": "tool_use", "id": "tu_1", "name": "request_permission",
                 "input": {"action": "Install npm package", "reason": "Need express"}},
            ],
            "stop_reason": "tool_use",
        }

        run_job(job.id)
        loaded = js.load_job(job.id)
        self.assertEqual(loaded.status, "blocked")
        self.assertEqual(len(loaded.permissions), 1)

    @patch("tools.lib.job_worker._call_anthropic")
    def test_api_error_fails_job(self, mock_api):
        """API error fails the job."""
        from tools.lib.job_worker import run_job

        job = js.create_job("Fail", "Do stuff", admin_id=123)
        mock_api.side_effect = RuntimeError("Anthropic API error 500: Server error")

        run_job(job.id)
        loaded = js.load_job(job.id)
        self.assertEqual(loaded.status, "failed")
        self.assertIn("API error", loaded.error)

    @patch("tools.lib.job_worker._call_anthropic")
    def test_text_only_response_blocks_for_review(self, mock_api):
        """If API returns text only (no complete tool), job gets blocked for admin review."""
        from tools.lib.job_worker import run_job

        job = js.create_job("Text", "Just chat", admin_id=123)
        mock_api.return_value = {
            "content": [{"type": "text", "text": "I'm done thinking."}],
            "stop_reason": "end_turn",
        }

        run_job(job.id)
        loaded = js.load_job(job.id)
        # Job didn't call complete, so it gets blocked for admin review
        self.assertEqual(loaded.status, "blocked")
        self.assertTrue(any("iteration limit" in p.action.lower() for p in loaded.permissions))

    @patch("tools.lib.job_worker._call_anthropic")
    @patch("tools.lib.job_worker.send_telegram")
    def test_max_iterations(self, mock_tg, mock_api):
        """Job that hits max iterations gets blocked with permission request."""
        from tools.lib.job_worker import run_job, MAX_ITERATIONS

        job = js.create_job("Long", "Long task", admin_id=123)

        # Always return a write_file (never completes)
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            return {
                "content": [
                    {"type": "tool_use", "id": f"tu_{call_count[0]}",
                     "name": "write_file",
                     "input": {"filename": f"iter_{call_count[0]}.txt",
                               "content": f"Iteration {call_count[0]}"}},
                ],
                "stop_reason": "tool_use",
            }

        mock_api.side_effect = side_effect

        run_job(job.id)
        loaded = js.load_job(job.id)
        self.assertEqual(loaded.status, "blocked")
        self.assertTrue(any("iteration limit" in p.action.lower() for p in loaded.permissions))

    @patch("tools.lib.job_worker._call_anthropic")
    def test_canceled_job_stops(self, mock_api):
        """If job is canceled externally during run, it stops."""
        from tools.lib.job_worker import run_job

        job = js.create_job("Cancel", "Do stuff", admin_id=123)

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Cancel the job after first API call
                loaded = js.load_job(job.id)
                loaded.status = "canceled"
                js.save_job(loaded)
                return {
                    "content": [
                        {"type": "tool_use", "id": "tu_1", "name": "write_file",
                         "input": {"filename": "a.txt", "content": "first"}},
                    ],
                    "stop_reason": "tool_use",
                }
            return {
                "content": [{"type": "text", "text": "Continuing..."}],
                "stop_reason": "end_turn",
            }

        mock_api.side_effect = side_effect

        run_job(job.id)
        loaded = js.load_job(job.id)
        self.assertEqual(loaded.status, "canceled")
        # Should have stopped after detecting cancellation
        self.assertEqual(call_count[0], 1)

    def test_run_nonexistent_job(self):
        from tools.lib.job_worker import run_job

        with self.assertRaises(ValueError):
            run_job("nonexistent")

    def test_run_completed_job(self):
        from tools.lib.job_worker import run_job

        job = js.create_job("Done", "Already done", admin_id=123)
        js.start_job(job)
        js.complete_job(job)

        with self.assertRaises(ValueError):
            run_job(job.id)


class TestResumeJob(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"resume_{id(self)}"
        js.JOBS_ROOT = self.jobs_root

    @patch("tools.lib.job_worker._call_anthropic")
    @patch("tools.lib.job_worker.send_telegram")
    def test_resume_running_job(self, mock_tg, mock_api):
        from tools.lib.job_worker import resume_job

        job = js.create_job("Resume", "Continue work", admin_id=123)
        js.start_job(job)

        mock_api.return_value = {
            "content": [
                {"type": "tool_use", "id": "tu_1", "name": "complete",
                 "input": {"summary": "Finished after resume"}},
            ],
            "stop_reason": "tool_use",
        }

        resume_job(job.id)
        loaded = js.load_job(job.id)
        self.assertEqual(loaded.status, "completed")

    def test_resume_blocked_job_fails(self):
        from tools.lib.job_worker import resume_job

        job = js.create_job("Blocked", "Blocked", admin_id=123)
        js.start_job(job)
        perm = js.PermissionRequest(perm_id="", job_id=job.id, action="Test", reason="Test")
        js.block_job(job, perm)

        with self.assertRaises(ValueError):
            resume_job(job.id)


class TestNotifications(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"notif_{id(self)}"
        js.JOBS_ROOT = self.jobs_root

    @patch("tools.lib.job_worker.send_telegram")
    def test_permission_notification(self, mock_tg):
        from tools.lib.job_worker import _notify_permission_request

        job = js.create_job("Notif", "test", admin_id=123)
        perm = js.PermissionRequest(
            perm_id="abc123", job_id=job.id,
            action="Delete files", reason="Cleanup",
            risk_level="high", safe_alternative="Skip cleanup",
        )
        _notify_permission_request(job, perm)
        mock_tg.assert_called_once()
        msg = mock_tg.call_args[0][0]
        self.assertIn("BLOCKED", msg)
        self.assertIn("Delete files", msg)
        self.assertIn("/approve abc123", msg)
        self.assertIn("/deny abc123", msg)
        self.assertIn("Skip cleanup", msg)

    @patch("tools.lib.job_worker.send_telegram")
    def test_completion_notification(self, mock_tg):
        from tools.lib.job_worker import _notify_completion

        job = js.create_job("Notif", "test", admin_id=123)
        js.start_job(job)
        js.complete_job(job, summary="All done")
        _notify_completion(job)
        mock_tg.assert_called_once()
        msg = mock_tg.call_args[0][0]
        self.assertIn("COMPLETED", msg)
        self.assertIn("All done", msg)

    @patch("tools.lib.job_worker.send_telegram", side_effect=Exception("Network error"))
    def test_notification_failure_ignored(self, mock_tg):
        """Notification failures should not crash the worker."""
        from tools.lib.job_worker import _notify_completion

        job = js.create_job("Notif fail", "test", admin_id=123)
        js.start_job(job)
        js.complete_job(job, summary="Done")
        # Should not raise
        _notify_completion(job)


if __name__ == "__main__":
    unittest.main()
