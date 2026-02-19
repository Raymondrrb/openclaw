#!/usr/bin/env python3
"""Tests for rayvault/io.py — shared I/O utilities."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from rayvault.io import (
    atomic_write_json, read_json, sha1_file, sha1_text, utc_now_iso,
    wav_duration_seconds,
)


class TestAtomicWriteJson(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_writes_valid_json(self):
        path = Path(self.tmpdir) / "test.json"
        data = {"key": "value", "number": 42}
        atomic_write_json(path, data)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["key"], "value")
        self.assertEqual(loaded["number"], 42)

    def test_creates_parent_dirs(self):
        path = Path(self.tmpdir) / "deep" / "nested" / "dir" / "test.json"
        atomic_write_json(path, {"ok": True})
        self.assertTrue(path.exists())
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(loaded["ok"])

    def test_no_tmp_file_left(self):
        path = Path(self.tmpdir) / "test.json"
        atomic_write_json(path, {"a": 1})
        tmp_files = list(Path(self.tmpdir).glob("*.tmp"))
        self.assertEqual(len(tmp_files), 0)

    def test_overwrites_existing(self):
        path = Path(self.tmpdir) / "test.json"
        atomic_write_json(path, {"version": 1})
        atomic_write_json(path, {"version": 2})
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["version"], 2)

    def test_handles_unicode(self):
        path = Path(self.tmpdir) / "test.json"
        atomic_write_json(path, {"emoji": "teste \u2764", "accent": "café"})
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["emoji"], "teste \u2764")
        self.assertEqual(loaded["accent"], "café")

    def test_trailing_newline(self):
        path = Path(self.tmpdir) / "test.json"
        atomic_write_json(path, {"a": 1})
        raw = path.read_bytes()
        self.assertTrue(raw.endswith(b"\n"))

    def test_indent_default_2(self):
        path = Path(self.tmpdir) / "test.json"
        atomic_write_json(path, {"a": 1})
        text = path.read_text(encoding="utf-8")
        self.assertIn("  ", text)  # 2-space indent

    def test_custom_indent(self):
        path = Path(self.tmpdir) / "test.json"
        atomic_write_json(path, {"a": 1}, indent=4)
        text = path.read_text(encoding="utf-8")
        self.assertIn("    ", text)  # 4-space indent

    def test_handles_list(self):
        path = Path(self.tmpdir) / "test.json"
        atomic_write_json(path, [1, 2, 3])
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded, [1, 2, 3])

    def test_handles_nested_structures(self):
        path = Path(self.tmpdir) / "test.json"
        data = {"products": [{"name": "A", "scores": [1.5, 2.3]}], "meta": {"version": "1.0"}}
        atomic_write_json(path, data)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded, data)

    def test_file_permissions(self):
        path = Path(self.tmpdir) / "test.json"
        atomic_write_json(path, {"a": 1})
        mode = os.stat(path).st_mode & 0o777
        self.assertEqual(mode, 0o644)

    def test_handles_empty_dict(self):
        path = Path(self.tmpdir) / "test.json"
        atomic_write_json(path, {})
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded, {})

    def test_handles_null_values(self):
        path = Path(self.tmpdir) / "test.json"
        atomic_write_json(path, {"key": None})
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsNone(loaded["key"])

    def test_returns_none(self):
        path = Path(self.tmpdir) / "test.json"
        result = atomic_write_json(path, {"a": 1})
        self.assertIsNone(result)


# ---------------------------------------------------------------
# utc_now_iso
# ---------------------------------------------------------------

class TestUtcNowIso(unittest.TestCase):

    def test_format(self):
        ts = utc_now_iso()
        self.assertTrue(ts.endswith("Z"))
        self.assertIn("T", ts)
        self.assertEqual(len(ts), 20)

    def test_deterministic_within_second(self):
        t1 = utc_now_iso()
        t2 = utc_now_iso()
        self.assertEqual(t1[:16], t2[:16])  # same up to minutes


# ---------------------------------------------------------------
# read_json
# ---------------------------------------------------------------

class TestReadJson(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_valid(self):
        p = Path(self.tmpdir) / "data.json"
        p.write_text('{"key": 42}', encoding="utf-8")
        self.assertEqual(read_json(p), {"key": 42})

    def test_missing(self):
        with self.assertRaises(FileNotFoundError):
            read_json(Path("/nonexistent.json"))

    def test_unicode(self):
        p = Path(self.tmpdir) / "data.json"
        p.write_text('{"text": "café"}', encoding="utf-8")
        self.assertEqual(read_json(p)["text"], "café")


# ---------------------------------------------------------------
# sha1_file
# ---------------------------------------------------------------

class TestSha1File(unittest.TestCase):

    def test_deterministic(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello world")
            p = Path(f.name)
        try:
            self.assertEqual(sha1_file(p), sha1_file(p))
            self.assertEqual(len(sha1_file(p)), 40)
        finally:
            p.unlink()

    def test_matches_hashlib(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test data")
            p = Path(f.name)
        try:
            expected = hashlib.sha1(b"test data").hexdigest()
            self.assertEqual(sha1_file(p), expected)
        finally:
            p.unlink()

    def test_different_content(self):
        with tempfile.NamedTemporaryFile(delete=False) as f1:
            f1.write(b"aaa")
            p1 = Path(f1.name)
        with tempfile.NamedTemporaryFile(delete=False) as f2:
            f2.write(b"bbb")
            p2 = Path(f2.name)
        try:
            self.assertNotEqual(sha1_file(p1), sha1_file(p2))
        finally:
            p1.unlink()
            p2.unlink()


# ---------------------------------------------------------------
# sha1_text
# ---------------------------------------------------------------

class TestSha1Text(unittest.TestCase):

    def test_deterministic(self):
        self.assertEqual(sha1_text("hello"), sha1_text("hello"))

    def test_hex_length(self):
        self.assertEqual(len(sha1_text("test")), 40)

    def test_different_input(self):
        self.assertNotEqual(sha1_text("a"), sha1_text("b"))

    def test_matches_hashlib(self):
        expected = hashlib.sha1(b"test").hexdigest()
        self.assertEqual(sha1_text("test"), expected)


# ---------------------------------------------------------------
# wav_duration_seconds
# ---------------------------------------------------------------

class TestWavDurationSeconds(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_missing_file(self):
        p = Path(self.tmpdir) / "nonexistent.wav"
        self.assertIsNone(wav_duration_seconds(p))

    def test_non_wav_file(self):
        p = Path(self.tmpdir) / "not_a_wav.txt"
        p.write_text("not audio data")
        self.assertIsNone(wav_duration_seconds(p))

    def test_valid_wav(self):
        import struct
        import wave
        p = Path(self.tmpdir) / "test.wav"
        rate = 44100
        n_frames = rate * 2  # 2 seconds
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(struct.pack(f"<{n_frames}h", *([0] * n_frames)))
        dur = wav_duration_seconds(p)
        self.assertIsNotNone(dur)
        self.assertAlmostEqual(dur, 2.0, places=1)

    def test_stereo_wav(self):
        import struct
        import wave
        p = Path(self.tmpdir) / "stereo.wav"
        rate = 48000
        n_frames = rate  # 1 second
        with wave.open(str(p), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(struct.pack(f"<{n_frames * 2}h", *([0] * n_frames * 2)))
        dur = wav_duration_seconds(p)
        self.assertIsNotNone(dur)
        self.assertAlmostEqual(dur, 1.0, places=1)


# ---------------------------------------------------------------
# read_json edge cases
# ---------------------------------------------------------------

class TestReadJsonEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_reads_list(self):
        p = Path(self.tmpdir) / "list.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(read_json(p), [1, 2, 3])

    def test_reads_nested(self):
        p = Path(self.tmpdir) / "nested.json"
        data = {"a": {"b": {"c": [1, 2]}}}
        p.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(read_json(p)["a"]["b"]["c"], [1, 2])

    def test_reads_null(self):
        p = Path(self.tmpdir) / "null.json"
        p.write_text("null", encoding="utf-8")
        self.assertIsNone(read_json(p))

    def test_invalid_json_raises(self):
        p = Path(self.tmpdir) / "bad.json"
        p.write_text("{not json}", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            read_json(p)

    def test_empty_object(self):
        p = Path(self.tmpdir) / "empty.json"
        p.write_text("{}", encoding="utf-8")
        self.assertEqual(read_json(p), {})


# ---------------------------------------------------------------
# sha1_text edge cases
# ---------------------------------------------------------------

class TestSha1TextEdgeCases(unittest.TestCase):

    def test_empty_string(self):
        expected = hashlib.sha1(b"").hexdigest()
        self.assertEqual(sha1_text(""), expected)

    def test_unicode(self):
        result = sha1_text("café")
        self.assertEqual(len(result), 40)

    def test_long_string(self):
        result = sha1_text("x" * 100000)
        self.assertEqual(len(result), 40)


# ---------------------------------------------------------------
# sha1_file edge cases
# ---------------------------------------------------------------

class TestSha1FileEdgeCases(unittest.TestCase):

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            p = Path(f.name)
        try:
            expected = hashlib.sha1(b"").hexdigest()
            self.assertEqual(sha1_file(p), expected)
        finally:
            p.unlink()

    def test_binary_content(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(bytes(range(256)))
            p = Path(f.name)
        try:
            result = sha1_file(p)
            self.assertEqual(len(result), 40)
        finally:
            p.unlink()


# ---------------------------------------------------------------
# atomic_write_json edge cases
# ---------------------------------------------------------------

class TestAtomicWriteJsonEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_large_data(self):
        path = Path(self.tmpdir) / "large.json"
        data = {"items": [{"id": i, "name": f"item_{i}"} for i in range(1000)]}
        atomic_write_json(path, data)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(loaded["items"]), 1000)

    def test_boolean_values(self):
        path = Path(self.tmpdir) / "bool.json"
        data = {"active": True, "deleted": False}
        atomic_write_json(path, data)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(loaded["active"])
        self.assertFalse(loaded["deleted"])

    def test_numeric_types(self):
        path = Path(self.tmpdir) / "nums.json"
        data = {"int": 42, "float": 3.14, "neg": -1, "zero": 0}
        atomic_write_json(path, data)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["float"], 3.14)
        self.assertEqual(loaded["neg"], -1)

    def test_ensure_ascii_false(self):
        path = Path(self.tmpdir) / "nonascii.json"
        atomic_write_json(path, {"text": "日本語"})
        raw = path.read_text(encoding="utf-8")
        self.assertIn("日本語", raw)  # should not be escaped


if __name__ == "__main__":
    unittest.main()
