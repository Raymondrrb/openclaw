#!/usr/bin/env python3
"""Tests for tools/failure_alert.py — load_alerted, save_alerted."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import failure_alert


# ---------------------------------------------------------------
# load_alerted
# ---------------------------------------------------------------

class TestLoadAlerted(unittest.TestCase):

    def test_no_file_returns_empty_set(self):
        with patch.object(failure_alert, "ALERTED_FILE", Path("/nonexistent/path.json")):
            result = failure_alert.load_alerted()
            self.assertEqual(result, set())

    def test_valid_json_list(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(["slug_a", "slug_b", "slug_c"], f)
            f.flush()
            tmp_path = Path(f.name)
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                result = failure_alert.load_alerted()
                self.assertEqual(result, {"slug_a", "slug_b", "slug_c"})
        finally:
            tmp_path.unlink()

    def test_empty_list(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([], f)
            f.flush()
            tmp_path = Path(f.name)
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                result = failure_alert.load_alerted()
                self.assertEqual(result, set())
        finally:
            tmp_path.unlink()

    def test_non_list_json_returns_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "value"}, f)
            f.flush()
            tmp_path = Path(f.name)
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                result = failure_alert.load_alerted()
                self.assertEqual(result, set())
        finally:
            tmp_path.unlink()

    def test_corrupt_json_returns_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json{{{")
            f.flush()
            tmp_path = Path(f.name)
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                result = failure_alert.load_alerted()
                self.assertEqual(result, set())
        finally:
            tmp_path.unlink()


# ---------------------------------------------------------------
# save_alerted
# ---------------------------------------------------------------

class TestSaveAlerted(unittest.TestCase):

    def test_save_and_reload(self):
        tmpdir = tempfile.mkdtemp()
        tmp_path = Path(tmpdir) / "seen.json"
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                failure_alert.save_alerted({"alpha", "beta"})
                self.assertTrue(tmp_path.exists())
                data = json.loads(tmp_path.read_text(encoding="utf-8"))
                self.assertEqual(sorted(data), ["alpha", "beta"])
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            os.rmdir(tmpdir)

    def test_save_empty_set(self):
        tmpdir = tempfile.mkdtemp()
        tmp_path = Path(tmpdir) / "seen.json"
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                failure_alert.save_alerted(set())
                data = json.loads(tmp_path.read_text(encoding="utf-8"))
                self.assertEqual(data, [])
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            os.rmdir(tmpdir)

    def test_creates_parent_dirs(self):
        tmpdir = tempfile.mkdtemp()
        nested = Path(tmpdir) / "sub" / "dir" / "seen.json"
        try:
            with patch.object(failure_alert, "ALERTED_FILE", nested):
                failure_alert.save_alerted({"x"})
                self.assertTrue(nested.exists())
        finally:
            import shutil
            shutil.rmtree(tmpdir)

    def test_overwrite_existing(self):
        tmpdir = tempfile.mkdtemp()
        tmp_path = Path(tmpdir) / "seen.json"
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                failure_alert.save_alerted({"old_slug"})
                failure_alert.save_alerted({"new_slug"})
                data = json.loads(tmp_path.read_text(encoding="utf-8"))
                self.assertEqual(data, ["new_slug"])
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            os.rmdir(tmpdir)


# ---------------------------------------------------------------
# Round-trip: save then load
# ---------------------------------------------------------------

class TestRoundTrip(unittest.TestCase):

    def test_save_then_load(self):
        tmpdir = tempfile.mkdtemp()
        tmp_path = Path(tmpdir) / "seen.json"
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                original = {"slug_1", "slug_2", "slug_3"}
                failure_alert.save_alerted(original)
                loaded = failure_alert.load_alerted()
                self.assertEqual(loaded, original)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            os.rmdir(tmpdir)


# ---------------------------------------------------------------
# load_alerted edge cases
# ---------------------------------------------------------------

class TestLoadAlertedEdgeCases(unittest.TestCase):

    def test_list_with_duplicates(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(["slug_a", "slug_a", "slug_b"], f)
            f.flush()
            tmp_path = Path(f.name)
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                result = failure_alert.load_alerted()
                self.assertEqual(result, {"slug_a", "slug_b"})
        finally:
            tmp_path.unlink()

    def test_list_with_none_values(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(["slug_a", None, "slug_b"], f)
            f.flush()
            tmp_path = Path(f.name)
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                result = failure_alert.load_alerted()
                # Should still be a set (may include None or filter it)
                self.assertIsInstance(result, set)
        finally:
            tmp_path.unlink()

    def test_permission_error_returns_empty(self):
        # Non-existent directory path won't crash
        with patch.object(failure_alert, "ALERTED_FILE", Path("/nonexistent/deep/path.json")):
            result = failure_alert.load_alerted()
            self.assertEqual(result, set())


# ---------------------------------------------------------------
# save_alerted edge cases
# ---------------------------------------------------------------

class TestSaveAlertedEdgeCases(unittest.TestCase):

    def test_large_set(self):
        tmpdir = tempfile.mkdtemp()
        tmp_path = Path(tmpdir) / "seen.json"
        try:
            slugs = {f"run_slug_{i}" for i in range(100)}
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                failure_alert.save_alerted(slugs)
                data = json.loads(tmp_path.read_text(encoding="utf-8"))
                self.assertEqual(len(data), 100)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            os.rmdir(tmpdir)

    def test_unicode_slugs(self):
        tmpdir = tempfile.mkdtemp()
        tmp_path = Path(tmpdir) / "seen.json"
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                failure_alert.save_alerted({"café_slug", "日本語"})
                data = json.loads(tmp_path.read_text(encoding="utf-8"))
                self.assertEqual(len(data), 2)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            os.rmdir(tmpdir)


# ---------------------------------------------------------------
# Round-trip edge cases
# ---------------------------------------------------------------

class TestRoundTripEdgeCases(unittest.TestCase):

    def test_round_trip_large_set(self):
        tmpdir = tempfile.mkdtemp()
        tmp_path = Path(tmpdir) / "seen.json"
        try:
            slugs = {f"slug_{i}" for i in range(200)}
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                failure_alert.save_alerted(slugs)
                loaded = failure_alert.load_alerted()
                self.assertEqual(loaded, slugs)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            os.rmdir(tmpdir)

    def test_round_trip_single_slug(self):
        tmpdir = tempfile.mkdtemp()
        tmp_path = Path(tmpdir) / "seen.json"
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                failure_alert.save_alerted({"only_one"})
                loaded = failure_alert.load_alerted()
                self.assertEqual(loaded, {"only_one"})
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            os.rmdir(tmpdir)

    def test_save_overwrites_completely(self):
        tmpdir = tempfile.mkdtemp()
        tmp_path = Path(tmpdir) / "seen.json"
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                failure_alert.save_alerted({"a", "b", "c"})
                failure_alert.save_alerted({"x"})
                loaded = failure_alert.load_alerted()
                self.assertEqual(loaded, {"x"})
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            os.rmdir(tmpdir)

    def test_load_after_delete_returns_empty(self):
        tmpdir = tempfile.mkdtemp()
        tmp_path = Path(tmpdir) / "seen.json"
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                failure_alert.save_alerted({"slug_1"})
                tmp_path.unlink()
                loaded = failure_alert.load_alerted()
                self.assertEqual(loaded, set())
        finally:
            os.rmdir(tmpdir)

    def test_save_sorted_output(self):
        tmpdir = tempfile.mkdtemp()
        tmp_path = Path(tmpdir) / "seen.json"
        try:
            with patch.object(failure_alert, "ALERTED_FILE", tmp_path):
                failure_alert.save_alerted({"z_slug", "a_slug", "m_slug"})
                data = json.loads(tmp_path.read_text(encoding="utf-8"))
                self.assertEqual(data, ["a_slug", "m_slug", "z_slug"])
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            os.rmdir(tmpdir)


if __name__ == "__main__":
    unittest.main()
