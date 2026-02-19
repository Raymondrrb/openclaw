#!/usr/bin/env python3
"""Tests for lib/common.py — shared pipeline utilities."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure tools/ is on the path so lib/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from lib.common import (
    project_root,
    now_iso,
    today_iso,
    load_json,
    save_json,
    load_jsonl,
    load_env_file,
    require_env,
    slugify,
    iso8601_duration_to_seconds,
)


# ---------------------------------------------------------------------------
# project_root
# ---------------------------------------------------------------------------

class TestProjectRoot(unittest.TestCase):
    def test_returns_path(self):
        result = project_root()
        self.assertIsInstance(result, Path)

    def test_env_override(self):
        with unittest.mock.patch.dict(os.environ, {"PROJECT_ROOT": "/tmp/test_root"}):
            self.assertEqual(project_root(), Path("/tmp/test_root"))


# ---------------------------------------------------------------------------
# now_iso / today_iso
# ---------------------------------------------------------------------------

class TestTimestamps(unittest.TestCase):
    def test_now_iso_format(self):
        result = now_iso()
        self.assertTrue(result.endswith("Z"))
        # Should parse back without error
        dt.datetime.fromisoformat(result.replace("Z", "+00:00"))

    def test_now_iso_no_microseconds(self):
        result = now_iso()
        self.assertNotIn(".", result)

    def test_today_iso(self):
        result = today_iso()
        self.assertEqual(len(result), 10)
        self.assertEqual(result, dt.date.today().isoformat())


# ---------------------------------------------------------------------------
# load_json / save_json
# ---------------------------------------------------------------------------

class TestLoadJson(unittest.TestCase):
    def test_load_existing(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "value"}, f)
            path = f.name
        try:
            result = load_json(path)
            self.assertEqual(result, {"key": "value"})
        finally:
            os.unlink(path)

    def test_load_missing_returns_default(self):
        result = load_json("/nonexistent/path.json", default={"fallback": True})
        self.assertEqual(result, {"fallback": True})

    def test_load_missing_returns_none_by_default(self):
        result = load_json("/nonexistent/path.json")
        self.assertIsNone(result)


class TestSaveJson(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            data = {"numbers": [1, 2, 3], "nested": {"a": True}}
            save_json(path, data)
            loaded = load_json(path)
            self.assertEqual(loaded, data)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# load_jsonl
# ---------------------------------------------------------------------------

class TestLoadJsonl(unittest.TestCase):
    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("")
            path = f.name
        try:
            self.assertEqual(load_jsonl(path), [])
        finally:
            os.unlink(path)

    def test_missing_file(self):
        self.assertEqual(load_jsonl("/nonexistent/data.jsonl"), [])

    def test_valid_rows(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"a": 1}\n{"b": 2}\n{"c": 3}\n')
            path = f.name
        try:
            result = load_jsonl(path)
            self.assertEqual(len(result), 3)
            self.assertEqual(result[0]["a"], 1)
        finally:
            os.unlink(path)

    def test_limit(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for i in range(10):
                f.write(json.dumps({"n": i}) + "\n")
            path = f.name
        try:
            result = load_jsonl(path, limit=3)
            self.assertEqual(len(result), 3)
            self.assertEqual(result[0]["n"], 7)  # Last 3: 7, 8, 9
        finally:
            os.unlink(path)

    def test_skips_invalid_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"valid": true}\nnot json\n{"also_valid": true}\n')
            path = f.name
        try:
            result = load_jsonl(path)
            self.assertEqual(len(result), 2)
        finally:
            os.unlink(path)

    def test_skips_blank_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"a": 1}\n\n\n{"b": 2}\n')
            path = f.name
        try:
            result = load_jsonl(path)
            self.assertEqual(len(result), 2)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# load_env_file
# ---------------------------------------------------------------------------

class TestLoadEnvFile(unittest.TestCase):
    def test_loads_vars(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("TEST_URL_SAFETY_VAR1=hello\nTEST_URL_SAFETY_VAR2=world\n")
            path = f.name
        try:
            # Clean up any existing env vars
            os.environ.pop("TEST_URL_SAFETY_VAR1", None)
            os.environ.pop("TEST_URL_SAFETY_VAR2", None)
            load_env_file(path)
            self.assertEqual(os.environ.get("TEST_URL_SAFETY_VAR1"), "hello")
            self.assertEqual(os.environ.get("TEST_URL_SAFETY_VAR2"), "world")
        finally:
            os.unlink(path)
            os.environ.pop("TEST_URL_SAFETY_VAR1", None)
            os.environ.pop("TEST_URL_SAFETY_VAR2", None)

    def test_does_not_overwrite(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("TEST_URL_SAFETY_EXISTING=new_value\n")
            path = f.name
        try:
            os.environ["TEST_URL_SAFETY_EXISTING"] = "original"
            load_env_file(path)
            self.assertEqual(os.environ["TEST_URL_SAFETY_EXISTING"], "original")
        finally:
            os.unlink(path)
            os.environ.pop("TEST_URL_SAFETY_EXISTING", None)

    def test_skips_comments_and_blanks(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("# Comment\n\nTEST_URL_SAFETY_KEY3=val\n")
            path = f.name
        try:
            os.environ.pop("TEST_URL_SAFETY_KEY3", None)
            load_env_file(path)
            self.assertEqual(os.environ.get("TEST_URL_SAFETY_KEY3"), "val")
        finally:
            os.unlink(path)
            os.environ.pop("TEST_URL_SAFETY_KEY3", None)

    def test_missing_file_no_error(self):
        load_env_file("/nonexistent/.env")  # Should not raise


# ---------------------------------------------------------------------------
# require_env
# ---------------------------------------------------------------------------

class TestRequireEnv(unittest.TestCase):
    def test_returns_value(self):
        os.environ["TEST_URL_SAFETY_REQ"] = "abc"
        try:
            self.assertEqual(require_env("TEST_URL_SAFETY_REQ"), "abc")
        finally:
            os.environ.pop("TEST_URL_SAFETY_REQ", None)

    def test_strips_whitespace(self):
        os.environ["TEST_URL_SAFETY_REQ2"] = "  trimmed  "
        try:
            self.assertEqual(require_env("TEST_URL_SAFETY_REQ2"), "trimmed")
        finally:
            os.environ.pop("TEST_URL_SAFETY_REQ2", None)

    def test_raises_on_missing(self):
        os.environ.pop("TEST_URL_SAFETY_MISSING", None)
        with self.assertRaises(RuntimeError):
            require_env("TEST_URL_SAFETY_MISSING")

    def test_raises_on_empty(self):
        os.environ["TEST_URL_SAFETY_EMPTY"] = "   "
        try:
            with self.assertRaises(RuntimeError):
                require_env("TEST_URL_SAFETY_EMPTY")
        finally:
            os.environ.pop("TEST_URL_SAFETY_EMPTY", None)


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------

class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello World"), "hello_world")

    def test_special_chars(self):
        self.assertEqual(slugify("desk & gadgets!"), "desk_gadgets")

    def test_max_length(self):
        result = slugify("a" * 100, max_len=10)
        self.assertLessEqual(len(result), 10)

    def test_strips_leading_trailing_underscores(self):
        result = slugify("  !!test!!  ")
        self.assertFalse(result.startswith("_"))
        self.assertFalse(result.endswith("_"))

    def test_collapses_multiple_underscores(self):
        result = slugify("a   b   c")
        self.assertNotIn("__", result)

    def test_empty_returns_value(self):
        result = slugify("!!!")
        self.assertEqual(result, "value")


# ---------------------------------------------------------------------------
# iso8601_duration_to_seconds
# ---------------------------------------------------------------------------

class TestIso8601DurationToSeconds(unittest.TestCase):
    def test_hours_minutes_seconds(self):
        self.assertEqual(iso8601_duration_to_seconds("PT1H30M15S"), 5415)

    def test_minutes_only(self):
        self.assertEqual(iso8601_duration_to_seconds("PT8M"), 480)

    def test_seconds_only(self):
        self.assertEqual(iso8601_duration_to_seconds("PT45S"), 45)

    def test_hours_only(self):
        self.assertEqual(iso8601_duration_to_seconds("PT2H"), 7200)

    def test_zero(self):
        self.assertEqual(iso8601_duration_to_seconds("PT0S"), 0)

    def test_no_time_designator(self):
        # Just "P" or empty-ish — should return 0
        self.assertEqual(iso8601_duration_to_seconds("PT"), 0)

    def test_minutes_seconds(self):
        self.assertEqual(iso8601_duration_to_seconds("PT12M30S"), 750)


# Need unittest.mock for project_root test
import unittest.mock  # noqa: E402


if __name__ == "__main__":
    unittest.main()
