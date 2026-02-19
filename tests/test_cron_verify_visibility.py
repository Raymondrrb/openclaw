#!/usr/bin/env python3
"""Tests for rayvault/cron_verify_visibility.py — batch scan."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rayvault.cron_verify_visibility import scan_uploaded_runs, utc_now_iso


# ---------------------------------------------------------------
# scan_uploaded_runs
# ---------------------------------------------------------------

class TestScanUploadedRuns(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.runs_root = Path(self._tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_run(self, name: str, status: str):
        run_dir = self.runs_root / name
        publish = run_dir / "publish"
        publish.mkdir(parents=True)
        receipt = {"status": status, "youtube": {"video_id": f"vid_{name}"}}
        (publish / "upload_receipt.json").write_text(
            json.dumps(receipt), encoding="utf-8"
        )
        return run_dir

    def test_empty_dir(self):
        self.assertEqual(scan_uploaded_runs(self.runs_root), [])

    def test_nonexistent_dir(self):
        self.assertEqual(scan_uploaded_runs(Path("/nonexistent")), [])

    def test_finds_uploaded(self):
        self._make_run("RUN_A", "UPLOADED")
        self._make_run("RUN_B", "VERIFIED")
        self._make_run("RUN_C", "UPLOADED")
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 2)
        names = {r.name for r in runs}
        self.assertEqual(names, {"RUN_A", "RUN_C"})

    def test_skips_verified(self):
        self._make_run("RUN_V", "VERIFIED")
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 0)

    def test_corrupt_receipt_skipped(self):
        run_dir = self.runs_root / "RUN_BAD"
        publish = run_dir / "publish"
        publish.mkdir(parents=True)
        (publish / "upload_receipt.json").write_text("not json")
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 0)

    def test_no_receipt_file(self):
        run_dir = self.runs_root / "RUN_NO_RECEIPT"
        publish = run_dir / "publish"
        publish.mkdir(parents=True)
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 0)

    def test_receipt_missing_status(self):
        run_dir = self.runs_root / "RUN_NO_STATUS"
        publish = run_dir / "publish"
        publish.mkdir(parents=True)
        (publish / "upload_receipt.json").write_text(
            json.dumps({"youtube": {"video_id": "v1"}}), encoding="utf-8"
        )
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 0)

    def test_receipt_failed_status(self):
        self._make_run("RUN_FAIL", "FAILED")
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 0)

    def test_multiple_uploaded_sorted(self):
        self._make_run("AAA_RUN", "UPLOADED")
        self._make_run("ZZZ_RUN", "UPLOADED")
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0].name, "AAA_RUN")
        self.assertEqual(runs[1].name, "ZZZ_RUN")

    def test_empty_receipt_file(self):
        run_dir = self.runs_root / "RUN_EMPTY"
        publish = run_dir / "publish"
        publish.mkdir(parents=True)
        (publish / "upload_receipt.json").write_text("", encoding="utf-8")
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 0)

    def test_no_publish_dir(self):
        run_dir = self.runs_root / "RUN_NO_PUB"
        run_dir.mkdir(parents=True)
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 0)


# ---------------------------------------------------------------
# utc_now_iso
# ---------------------------------------------------------------

class TestUtcNowIso(unittest.TestCase):

    def test_format(self):
        ts = utc_now_iso()
        self.assertTrue(ts.endswith("Z"))
        self.assertIn("T", ts)


# ---------------------------------------------------------------
# scan_uploaded_runs edge cases
# ---------------------------------------------------------------

class TestScanUploadedRunsEdgeCases(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.runs_root = Path(self._tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_run(self, name: str, status: str):
        run_dir = self.runs_root / name
        publish = run_dir / "publish"
        publish.mkdir(parents=True)
        receipt = {"status": status, "youtube": {"video_id": f"vid_{name}"}}
        (publish / "upload_receipt.json").write_text(
            json.dumps(receipt), encoding="utf-8"
        )
        return run_dir

    def test_deeply_nested_not_scanned(self):
        # Only immediate children should be scanned
        nested = self.runs_root / "deep" / "RUN_NESTED"
        publish = nested / "publish"
        publish.mkdir(parents=True)
        (publish / "upload_receipt.json").write_text(
            json.dumps({"status": "UPLOADED", "youtube": {"video_id": "v"}}),
            encoding="utf-8",
        )
        runs = scan_uploaded_runs(self.runs_root)
        # Only "deep" is a direct child, not RUN_NESTED
        uploaded_names = {r.name for r in runs}
        self.assertNotIn("RUN_NESTED", uploaded_names)

    def test_non_directory_children_ignored(self):
        (self.runs_root / "stray_file.txt").write_text("not a run")
        self._make_run("RUN_REAL", "UPLOADED")
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 1)

    def test_mixed_statuses(self):
        self._make_run("RUN_A", "UPLOADED")
        self._make_run("RUN_B", "VERIFIED")
        self._make_run("RUN_C", "FAILED")
        self._make_run("RUN_D", "UPLOADED")
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 2)

    def test_receipt_is_array(self):
        run_dir = self.runs_root / "RUN_ARR"
        publish = run_dir / "publish"
        publish.mkdir(parents=True)
        (publish / "upload_receipt.json").write_text("[]", encoding="utf-8")
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 0)

    def test_receipt_status_case_sensitive(self):
        # "uploaded" (lowercase) should NOT match
        run_dir = self.runs_root / "RUN_LC"
        publish = run_dir / "publish"
        publish.mkdir(parents=True)
        (publish / "upload_receipt.json").write_text(
            json.dumps({"status": "uploaded", "youtube": {"video_id": "v"}}),
            encoding="utf-8",
        )
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 0)

    def test_hidden_dirs_ignored(self):
        # Hidden directories should not be scanned
        hidden = self.runs_root / ".hidden_run"
        publish = hidden / "publish"
        publish.mkdir(parents=True)
        (publish / "upload_receipt.json").write_text(
            json.dumps({"status": "UPLOADED", "youtube": {"video_id": "v"}}),
            encoding="utf-8",
        )
        self._make_run("REAL_RUN", "UPLOADED")
        runs = scan_uploaded_runs(self.runs_root)
        names = {r.name for r in runs}
        self.assertIn("REAL_RUN", names)

    def test_many_runs_performance(self):
        for i in range(20):
            self._make_run(f"RUN_{i:03d}", "UPLOADED" if i % 2 == 0 else "VERIFIED")
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 10)

    def test_receipt_with_extra_fields(self):
        run_dir = self.runs_root / "RUN_EXTRA"
        publish = run_dir / "publish"
        publish.mkdir(parents=True)
        receipt = {
            "status": "UPLOADED",
            "youtube": {"video_id": "vid1", "url": "https://youtube.com/watch?v=vid1"},
            "uploaded_at": "2026-02-16T10:00:00Z",
            "extra_field": True,
        }
        (publish / "upload_receipt.json").write_text(
            json.dumps(receipt), encoding="utf-8"
        )
        runs = scan_uploaded_runs(self.runs_root)
        self.assertEqual(len(runs), 1)


if __name__ == "__main__":
    unittest.main()
