"""Tests for tools.lib.job_system — Telegram job/task control system."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Patch JOBS_ROOT before importing to use temp directory
_TEMP_DIR = tempfile.mkdtemp()

import tools.lib.job_system as js

# Override JOBS_ROOT for all tests
js.JOBS_ROOT = Path(_TEMP_DIR) / "test_jobs"


class TestJobLifecycle(unittest.TestCase):

    def setUp(self):
        """Fresh jobs dir for each test."""
        self.jobs_root = Path(_TEMP_DIR) / f"jobs_{id(self)}"
        js.JOBS_ROOT = self.jobs_root

    def test_create_job(self):
        job = js.create_job("Test job", "Do something", admin_id=5853624777)
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.title, "Test job")
        self.assertEqual(job.prompt, "Do something")
        self.assertEqual(job.admin_id, 5853624777)
        self.assertTrue(job.workspace.is_dir())
        self.assertTrue((job.workspace / "artifacts").is_dir())
        self.assertTrue((job.workspace / "logs.txt").is_file())

    def test_save_and_load_job(self):
        job = js.create_job("Persist test", "prompt", admin_id=123)
        loaded = js.load_job(job.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.title, "Persist test")
        self.assertEqual(loaded.status, "queued")

    def test_start_job(self):
        job = js.create_job("Start test", "prompt", admin_id=123)
        js.start_job(job)
        self.assertEqual(job.status, "running")
        self.assertTrue(job.started_at)

    def test_complete_job(self):
        job = js.create_job("Complete test", "prompt", admin_id=123)
        js.start_job(job)
        js.complete_job(job, summary="All done")
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.progress_percent, 100)
        self.assertEqual(job.checkpoint, "All done")
        self.assertTrue(job.completed_at)

    def test_fail_job(self):
        job = js.create_job("Fail test", "prompt", admin_id=123)
        js.start_job(job)
        js.fail_job(job, "Something went wrong")
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error, "Something went wrong")

    def test_cancel_job(self):
        job = js.create_job("Cancel test", "prompt", admin_id=123)
        js.cancel_job(job)
        self.assertEqual(job.status, "canceled")

    def test_list_jobs(self):
        js.create_job("Job 1", "p", admin_id=123)
        js.create_job("Job 2", "p", admin_id=123)
        js.create_job("Job 3", "p", admin_id=123)
        jobs = js.list_jobs(limit=10)
        self.assertEqual(len(jobs), 3)

    def test_list_jobs_by_status(self):
        j1 = js.create_job("Q1", "p", admin_id=123)
        j2 = js.create_job("R1", "p", admin_id=123)
        js.start_job(j2)
        queued = js.list_jobs(status="queued")
        running = js.list_jobs(status="running")
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0].title, "Q1")
        self.assertEqual(len(running), 1)
        self.assertEqual(running[0].title, "R1")


class TestPermissions(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"perms_{id(self)}"
        js.JOBS_ROOT = self.jobs_root

    def test_block_job_with_permission(self):
        job = js.create_job("Perm test", "p", admin_id=123)
        js.start_job(job)
        perm = js.PermissionRequest(
            perm_id="",
            job_id=job.id,
            action="Install npm package",
            reason="Need express for server",
            risk_level="medium",
        )
        js.block_job(job, perm)
        self.assertEqual(job.status, "blocked")
        self.assertEqual(len(job.permissions), 1)
        self.assertIsNone(job.permissions[0].approved)

    def test_approve_permission_unblocks_job(self):
        job = js.create_job("Approve test", "p", admin_id=123)
        js.start_job(job)
        perm = js.PermissionRequest(
            perm_id="",
            job_id=job.id,
            action="Test action",
            reason="Test",
        )
        js.block_job(job, perm)
        perm_id = job.permissions[0].perm_id

        result_job, result_perm = js.approve_permission(perm_id)
        self.assertIsNotNone(result_job)
        self.assertTrue(result_perm.approved)
        self.assertEqual(result_job.status, "running")

    def test_deny_permission_keeps_blocked(self):
        job = js.create_job("Deny test", "p", admin_id=123)
        js.start_job(job)
        perm = js.PermissionRequest(
            perm_id="",
            job_id=job.id,
            action="Test action",
            reason="Test",
        )
        js.block_job(job, perm)
        perm_id = job.permissions[0].perm_id

        result_job, result_perm = js.deny_permission(perm_id)
        self.assertIsNotNone(result_job)
        self.assertFalse(result_perm.approved)
        # Job stays blocked (worker must handle denial)
        self.assertEqual(result_job.status, "blocked")

    def test_list_pending_permissions(self):
        job = js.create_job("Pending test", "p", admin_id=123)
        js.start_job(job)
        perm = js.PermissionRequest(
            perm_id="",
            job_id=job.id,
            action="Test",
            reason="Test",
        )
        js.block_job(job, perm)
        pending = js.list_pending_permissions()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0][0].id, job.id)

    def test_approve_nonexistent_perm(self):
        job, perm = js.approve_permission("nonexistent")
        self.assertIsNone(job)
        self.assertIsNone(perm)


class TestArtifacts(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"arts_{id(self)}"
        js.JOBS_ROOT = self.jobs_root

    def test_add_artifact(self):
        job = js.create_job("Art test", "p", admin_id=123)
        art = js.add_artifact(job, "report.md", "# Report\nContent here", "text/markdown")
        self.assertEqual(art.name, "report.md")
        self.assertTrue(Path(art.path).is_file())
        self.assertEqual(len(job.artifacts), 1)

    def test_artifact_persisted(self):
        job = js.create_job("Art persist", "p", admin_id=123)
        js.add_artifact(job, "data.json", '{"key": "value"}', "application/json")
        loaded = js.load_job(job.id)
        self.assertEqual(len(loaded.artifacts), 1)
        self.assertEqual(loaded.artifacts[0].name, "data.json")


class TestLogs(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"logs_{id(self)}"
        js.JOBS_ROOT = self.jobs_root

    def test_append_and_read_logs(self):
        job = js.create_job("Log test", "p", admin_id=123)
        js.append_log(job, "First entry")
        js.append_log(job, "Second entry")
        logs = js.read_logs(job, last_n=50)
        self.assertIn("First entry", logs)
        self.assertIn("Second entry", logs)

    def test_read_last_n_lines(self):
        job = js.create_job("Log limit", "p", admin_id=123)
        for i in range(10):
            js.append_log(job, f"Line {i}")
        logs = js.read_logs(job, last_n=3)
        lines = [l for l in logs.strip().split("\n") if l.strip()]
        self.assertEqual(len(lines), 3)
        self.assertIn("Line 9", lines[-1])


class TestAccessControl(unittest.TestCase):

    def test_admin_check(self):
        self.assertTrue(js.is_admin(5853624777))
        self.assertFalse(js.is_admin(99999))

    def test_rate_limit(self):
        root = Path(_TEMP_DIR) / f"rate_{id(self)}"
        js.JOBS_ROOT = root
        # Create jobs below limit
        for i in range(js.MAX_JOBS_PER_HOUR - 1):
            js.create_job(f"Rate {i}", "p", admin_id=5853624777)
        self.assertIsNone(js.check_rate_limit(5853624777))

        # Hit limit
        js.create_job("Rate limit", "p", admin_id=5853624777)
        self.assertIsNotNone(js.check_rate_limit(5853624777))

    def test_concurrency_limit(self):
        root = Path(_TEMP_DIR) / f"conc_{id(self)}"
        js.JOBS_ROOT = root
        self.assertIsNone(js.check_concurrency())

        job = js.create_job("Conc test", "p", admin_id=123)
        js.start_job(job)
        self.assertIsNotNone(js.check_concurrency())


class TestStudyTemplate(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"study_{id(self)}"
        js.JOBS_ROOT = self.jobs_root

    def test_study_plan_generation(self):
        plan = js.create_study_plan("Dzine AI best practices")
        self.assertIn("Dzine AI best practices", plan)
        self.assertIn("Phase 1", plan)
        self.assertIn("Phase 2", plan)
        self.assertIn("Phase 3", plan)
        self.assertIn("Done Criteria", plan)

    def test_init_study_workspace(self):
        job = js.create_job("Study Dzine", "Study Dzine AI", admin_id=123, job_type="study")
        js.init_study_workspace(job, "Dzine AI")
        ws = job.workspace
        self.assertTrue((ws / "plan.md").is_file())
        self.assertTrue((ws / "sources.json").is_file())
        self.assertTrue((ws / "output.md").is_file())
        self.assertTrue((ws / "notes.md").is_file())
        self.assertEqual(len(job.artifacts), 1)
        self.assertEqual(job.artifacts[0].name, "plan.md")


class TestAuditLog(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"audit_{id(self)}"
        js.JOBS_ROOT = self.jobs_root

    def test_log_admin_action(self):
        js.log_admin_action(5853624777, "task", {"title": "Test"})
        log_path = self.jobs_root / "admin_actions.jsonl"
        self.assertTrue(log_path.is_file())
        line = log_path.read_text(encoding="utf-8").strip()
        entry = json.loads(line)
        self.assertEqual(entry["admin_id"], 5853624777)
        self.assertEqual(entry["action"], "task")


class TestFormatting(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"fmt_{id(self)}"
        js.JOBS_ROOT = self.jobs_root

    def test_format_job_status(self):
        job = js.create_job("Format test", "p", admin_id=123)
        text = js.format_job_status(job)
        self.assertIn("Format test", text)
        self.assertIn("QUEUED", text)

    def test_format_job_list(self):
        js.create_job("A", "p", admin_id=123)
        js.create_job("B", "p", admin_id=123)
        jobs = js.list_jobs()
        text = js.format_job_list(jobs)
        self.assertIn("A", text)
        self.assertIn("B", text)

    def test_format_empty_list(self):
        text = js.format_job_list([])
        self.assertEqual(text, "No jobs found.")

    def test_format_permissions(self):
        job = js.create_job("Perm fmt", "p", admin_id=123)
        perm = js.PermissionRequest(
            perm_id="abc123",
            job_id=job.id,
            action="Install package",
            reason="Needed for analysis",
            risk_level="medium",
        )
        pending = [(job, perm)]
        text = js.format_permission_list(pending)
        self.assertIn("Install package", text)
        self.assertIn("/approve abc123", text)
        self.assertIn("/deny abc123", text)


class TestJobSerialization(unittest.TestCase):

    def test_job_round_trip(self):
        """Job → dict → Job preserves all fields."""
        job = js.Job(
            id="test123",
            title="Round trip",
            prompt="Do stuff",
            status="running",
            progress_percent=42,
            admin_id=5853624777,
            job_type="study",
        )
        job.artifacts.append(js.Artifact(name="a.md", path="/tmp/a.md"))
        job.permissions.append(js.PermissionRequest(
            perm_id="p1",
            job_id="test123",
            action="Test",
            reason="Why",
        ))
        job.instructions.append("Do this too")

        d = job.to_dict()
        restored = js.Job.from_dict(d)

        self.assertEqual(restored.id, "test123")
        self.assertEqual(restored.title, "Round trip")
        self.assertEqual(restored.status, "running")
        self.assertEqual(restored.progress_percent, 42)
        self.assertEqual(len(restored.artifacts), 1)
        self.assertEqual(len(restored.permissions), 1)
        self.assertEqual(len(restored.instructions), 1)
        self.assertEqual(restored.instructions[0], "Do this too")


if __name__ == "__main__":
    unittest.main()
