"""Tests for skills.rayviews-ops.scripts.ops — Telegram command handler."""

import sys
import tempfile
import unittest
from pathlib import Path

# Patch JOBS_ROOT before importing
_TEMP_DIR = tempfile.mkdtemp()

import tools.lib.job_system as js

# Ensure the skill module is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "rayviews-ops"))

from scripts.ops import handle_command


class TestCommandRouter(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"ops_{id(self)}"
        js.JOBS_ROOT = self.jobs_root
        self.admin_id = 5853624777

    def test_unauthorized_user(self):
        result = handle_command("/help", admin_id=99999)
        self.assertEqual(result, "Unauthorized.")

    def test_empty_command(self):
        result = handle_command("", admin_id=self.admin_id)
        self.assertEqual(result, "Empty command.")

    def test_unknown_command(self):
        result = handle_command("/foo", admin_id=self.admin_id)
        self.assertIn("Unknown command", result)

    def test_help(self):
        result = handle_command("/help", admin_id=self.admin_id)
        self.assertIn("Job Control", result)
        self.assertIn("/task", result)
        self.assertIn("Pipeline", result)


class TestTaskCommand(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"task_{id(self)}"
        js.JOBS_ROOT = self.jobs_root
        self.admin_id = 5853624777

    def test_create_general_task(self):
        result = handle_command("/task Fix the build system", admin_id=self.admin_id)
        self.assertIn("Job created", result)
        self.assertIn("Type: general", result)

    def test_create_study_task(self):
        result = handle_command("/task Study Dzine AI best practices", admin_id=self.admin_id)
        self.assertIn("Job created", result)
        self.assertIn("Type: study", result)
        self.assertIn("study workspace initialized", result.lower())

    def test_task_no_args(self):
        result = handle_command("/task", admin_id=self.admin_id)
        self.assertIn("Usage", result)

    def test_task_with_bang_prefix(self):
        result = handle_command("!task Build something", admin_id=self.admin_id)
        self.assertIn("Job created", result)


class TestStatusCommand(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"stat_{id(self)}"
        js.JOBS_ROOT = self.jobs_root
        self.admin_id = 5853624777

    def test_status_by_id(self):
        job = js.create_job("Status test", "p", admin_id=self.admin_id)
        result = handle_command(f"/status {job.id}", admin_id=self.admin_id)
        self.assertIn("Status test", result)
        self.assertIn("QUEUED", result)

    def test_status_latest(self):
        js.create_job("Latest", "p", admin_id=self.admin_id)
        result = handle_command("/status", admin_id=self.admin_id)
        self.assertIn("Latest", result)

    def test_status_not_found(self):
        result = handle_command("/status nonexistent", admin_id=self.admin_id)
        self.assertIn("not found", result)


class TestListCommand(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"list_{id(self)}"
        js.JOBS_ROOT = self.jobs_root
        self.admin_id = 5853624777

    def test_list_empty(self):
        result = handle_command("/list", admin_id=self.admin_id)
        self.assertIn("No jobs", result)

    def test_list_with_jobs(self):
        js.create_job("A", "p", admin_id=self.admin_id)
        js.create_job("B", "p", admin_id=self.admin_id)
        result = handle_command("/list", admin_id=self.admin_id)
        self.assertIn("A", result)
        self.assertIn("B", result)


class TestCancelCommand(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"cancel_{id(self)}"
        js.JOBS_ROOT = self.jobs_root
        self.admin_id = 5853624777

    def test_cancel_job(self):
        job = js.create_job("Cancel me", "p", admin_id=self.admin_id)
        result = handle_command(f"/cancel {job.id}", admin_id=self.admin_id)
        self.assertIn("canceled", result)
        loaded = js.load_job(job.id)
        self.assertEqual(loaded.status, "canceled")

    def test_cancel_completed_job(self):
        job = js.create_job("Done", "p", admin_id=self.admin_id)
        js.start_job(job)
        js.complete_job(job)
        result = handle_command(f"/cancel {job.id}", admin_id=self.admin_id)
        self.assertIn("already completed", result)


class TestContinueCommand(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"cont_{id(self)}"
        js.JOBS_ROOT = self.jobs_root
        self.admin_id = 5853624777

    def test_continue_running_job(self):
        job = js.create_job("Continue me", "p", admin_id=self.admin_id)
        js.start_job(job)
        result = handle_command(f"/continue {job.id} Go deeper on topic X", admin_id=self.admin_id)
        self.assertIn("Instruction added", result)
        loaded = js.load_job(job.id)
        self.assertEqual(len(loaded.instructions), 1)
        self.assertIn("Go deeper", loaded.instructions[0])

    def test_continue_no_args(self):
        result = handle_command("/continue", admin_id=self.admin_id)
        self.assertIn("Usage", result)


class TestPermissionCommands(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"perm_{id(self)}"
        js.JOBS_ROOT = self.jobs_root
        self.admin_id = 5853624777

    def test_approve_flow(self):
        job = js.create_job("Perm test", "p", admin_id=self.admin_id)
        js.start_job(job)
        perm = js.PermissionRequest(
            perm_id="",
            job_id=job.id,
            action="Install package",
            reason="Needed",
        )
        js.block_job(job, perm)
        perm_id = job.permissions[0].perm_id

        result = handle_command(f"/approve {perm_id}", admin_id=self.admin_id)
        self.assertIn("Approved", result)
        loaded = js.load_job(job.id)
        self.assertEqual(loaded.status, "running")

    def test_deny_flow(self):
        job = js.create_job("Deny test", "p", admin_id=self.admin_id)
        js.start_job(job)
        perm = js.PermissionRequest(
            perm_id="",
            job_id=job.id,
            action="Delete files",
            reason="Cleanup",
        )
        js.block_job(job, perm)
        perm_id = job.permissions[0].perm_id

        result = handle_command(f"/deny {perm_id}", admin_id=self.admin_id)
        self.assertIn("Denied", result)

    def test_pending_empty(self):
        result = handle_command("/pending", admin_id=self.admin_id)
        self.assertIn("No pending", result)

    def test_pending_with_requests(self):
        job = js.create_job("Pending test", "p", admin_id=self.admin_id)
        js.start_job(job)
        perm = js.PermissionRequest(
            perm_id="",
            job_id=job.id,
            action="Run script",
            reason="Analysis",
        )
        js.block_job(job, perm)
        result = handle_command("/pending", admin_id=self.admin_id)
        self.assertIn("Run script", result)


class TestPipelineCommands(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"pipe_{id(self)}"
        js.JOBS_ROOT = self.jobs_root
        self.admin_id = 5853624777

    def test_run_no_args(self):
        result = handle_command("/run", admin_id=self.admin_id)
        self.assertIn("Usage", result)

    def test_run_unknown_stage(self):
        result = handle_command("/run banana v001", admin_id=self.admin_id)
        self.assertIn("Unknown stage", result)

    def test_run_full_requires_confirmation(self):
        result = handle_command("/run run v001", admin_id=self.admin_id)
        self.assertIn("requires confirmation", result)
        self.assertIn("/confirm", result)

    def test_run_day_requires_confirmation(self):
        result = handle_command("/run day v001", admin_id=self.admin_id)
        self.assertIn("requires confirmation", result)

    def test_pipeline_status_no_args(self):
        result = handle_command("/pipeline-status", admin_id=self.admin_id)
        self.assertIn("Usage", result)


class TestArtifactCommands(unittest.TestCase):

    def setUp(self):
        self.jobs_root = Path(_TEMP_DIR) / f"artcmd_{id(self)}"
        js.JOBS_ROOT = self.jobs_root
        self.admin_id = 5853624777

    def test_artifacts_empty(self):
        job = js.create_job("No arts", "p", admin_id=self.admin_id)
        result = handle_command(f"/artifacts {job.id}", admin_id=self.admin_id)
        self.assertIn("no artifacts", result)

    def test_artifacts_with_files(self):
        job = js.create_job("With arts", "p", admin_id=self.admin_id)
        js.add_artifact(job, "report.md", "# Report", "text/markdown")
        result = handle_command(f"/artifacts {job.id}", admin_id=self.admin_id)
        self.assertIn("report.md", result)

    def test_get_artifact(self):
        job = js.create_job("Get art", "p", admin_id=self.admin_id)
        js.add_artifact(job, "data.txt", "Hello world", "text/plain")
        result = handle_command(f"/get {job.id} data.txt", admin_id=self.admin_id)
        self.assertIn("Hello world", result)

    def test_get_missing_artifact(self):
        job = js.create_job("Miss art", "p", admin_id=self.admin_id)
        result = handle_command(f"/get {job.id} nonexistent.txt", admin_id=self.admin_id)
        self.assertIn("not found", result)


if __name__ == "__main__":
    unittest.main()
