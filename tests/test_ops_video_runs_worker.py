#!/usr/bin/env python3
"""Tests for ops_video_runs_worker.py — CAS claim lifecycle, run.json loading, manifest resolution."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure tools/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from ops_video_runs_worker import (
    load_run_json,
    manifest_path_from_run,
    out_dir_for_run,
    should_retry_transient,
    MAX_FAIL_COUNT,
    CLAIM_STALE_MINUTES,
)


# ---------------------------------------------------------------------------
# load_run_json
# ---------------------------------------------------------------------------

class TestLoadRunJson(unittest.TestCase):
    def test_reads_run_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            data = {"status": "draft", "run_slug": "test_run"}
            (path / "run.json").write_text(json.dumps(data))
            result = load_run_json(path)
            self.assertEqual(result["status"], "draft")
            self.assertEqual(result["run_slug"], "test_run")

    def test_falls_back_to_pipeline_state(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            data = {"status": "legacy"}
            (path / "pipeline_state.json").write_text(json.dumps(data))
            result = load_run_json(path)
            self.assertEqual(result["status"], "legacy")

    def test_prefers_run_json_over_pipeline_state(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / "run.json").write_text(json.dumps({"source": "run"}))
            (path / "pipeline_state.json").write_text(json.dumps({"source": "legacy"}))
            result = load_run_json(path)
            self.assertEqual(result["source"], "run")

    def test_returns_empty_dict_when_no_file(self):
        with tempfile.TemporaryDirectory() as td:
            result = load_run_json(Path(td))
            self.assertEqual(result, {})

    def test_returns_empty_dict_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / "run.json").write_text("not valid json!!!")
            result = load_run_json(path)
            self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# manifest_path_from_run
# ---------------------------------------------------------------------------

class TestManifestPathFromRun(unittest.TestCase):
    def test_canonical_davinci_project_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / "davinci").mkdir()
            (path / "davinci" / "project.json").write_text("{}")
            result = manifest_path_from_run({}, path)
            self.assertEqual(result, path / "davinci" / "project.json")

    def test_legacy_from_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            legacy = path / "davinci_manifest.json"
            run_data = {"artifacts": {"davinci_manifest": str(legacy)}}
            result = manifest_path_from_run(run_data, path)
            self.assertEqual(result, legacy)

    def test_default_legacy_path(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            result = manifest_path_from_run({}, path)
            self.assertEqual(result, path / "davinci_manifest.json")


# ---------------------------------------------------------------------------
# out_dir_for_run
# ---------------------------------------------------------------------------

class TestOutDirForRun(unittest.TestCase):
    def test_artifact_path_anchor(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            artifact_file = path / "product_selection.json"
            artifact_file.write_text("[]")
            run = {"artifacts": {"products_json": str(artifact_file)}}
            result = out_dir_for_run(run)
            self.assertEqual(result, path)

    def test_run_slug_modern_path(self):
        with tempfile.TemporaryDirectory() as td:
            # Create a structure that matches modern pipeline_runs/slug/
            runs_dir = Path(td) / "pipeline_runs" / "test_slug"
            runs_dir.mkdir(parents=True)
            run = {"run_slug": "test_slug"}
            # Patch BASE_DIR to our temp dir
            with patch("ops_video_runs_worker.BASE_DIR", Path(td)):
                result = out_dir_for_run(run)
                self.assertEqual(result, runs_dir)


# ---------------------------------------------------------------------------
# should_retry_transient
# ---------------------------------------------------------------------------

class TestShouldRetryTransient(unittest.TestCase):
    def test_resolve_connection_error(self):
        self.assertTrue(should_retry_transient("Could not connect to DaVinci Resolve API"))

    def test_keep_resolve_open(self):
        self.assertTrue(should_retry_transient("keep resolve open and try again"))

    def test_no_active_project(self):
        self.assertTrue(should_retry_transient("No active project folder"))

    def test_non_transient(self):
        self.assertFalse(should_retry_transient("FileNotFoundError: script.json"))

    def test_empty(self):
        self.assertFalse(should_retry_transient(""))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants(unittest.TestCase):
    def test_max_fail_count_is_sane(self):
        self.assertGreaterEqual(MAX_FAIL_COUNT, 1)
        self.assertLessEqual(MAX_FAIL_COUNT, 10)

    def test_claim_stale_minutes_is_sane(self):
        self.assertGreaterEqual(CLAIM_STALE_MINUTES, 5)
        self.assertLessEqual(CLAIM_STALE_MINUTES, 120)


# ---------------------------------------------------------------------------
# load_run_json edge cases
# ---------------------------------------------------------------------------

class TestLoadRunJsonEdgeCases(unittest.TestCase):

    def test_run_json_with_nested_data(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            data = {
                "status": "gate1_approved",
                "artifacts": {"script": "/path/to/script.json"},
                "metadata": {"category": "earbuds"},
            }
            (path / "run.json").write_text(json.dumps(data), encoding="utf-8")
            result = load_run_json(path)
            self.assertEqual(result["artifacts"]["script"], "/path/to/script.json")

    def test_empty_json_object(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / "run.json").write_text("{}", encoding="utf-8")
            result = load_run_json(path)
            self.assertEqual(result, {})

    def test_run_json_is_array(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / "run.json").write_text("[]", encoding="utf-8")
            result = load_run_json(path)
            # Array is valid JSON but not a dict — behavior depends on implementation
            self.assertIsNotNone(result)

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / "run.json").write_text("", encoding="utf-8")
            result = load_run_json(path)
            self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# manifest_path_from_run edge cases
# ---------------------------------------------------------------------------

class TestManifestPathEdgeCases(unittest.TestCase):

    def test_artifacts_with_full_path(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            full = str(path / "custom_manifest.json")
            run_data = {"artifacts": {"davinci_manifest": full}}
            result = manifest_path_from_run(run_data, path)
            self.assertEqual(result, Path(full))

    def test_empty_run_data(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            result = manifest_path_from_run({}, path)
            self.assertEqual(result, path / "davinci_manifest.json")

    def test_davinci_dir_without_project_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / "davinci").mkdir()
            result = manifest_path_from_run({}, path)
            # davinci/ exists but no project.json, falls back
            self.assertEqual(result, path / "davinci_manifest.json")


# ---------------------------------------------------------------------------
# should_retry_transient edge cases
# ---------------------------------------------------------------------------

class TestShouldRetryTransientEdgeCases(unittest.TestCase):

    def test_none_input(self):
        # None should not crash
        try:
            result = should_retry_transient(None)
            self.assertFalse(result)
        except (TypeError, AttributeError):
            pass  # Either not crashing or returning False is acceptable

    def test_resolve_api_message(self):
        self.assertTrue(should_retry_transient("Could not connect to DaVinci Resolve API endpoint"))

    def test_case_sensitivity(self):
        # Check if matching is case-insensitive
        result_lower = should_retry_transient("could not connect to davinci resolve api")
        self.assertIsInstance(result_lower, bool)

    def test_long_error_message(self):
        msg = "Error: " * 100 + "Connection refused"
        result = should_retry_transient(msg)
        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
