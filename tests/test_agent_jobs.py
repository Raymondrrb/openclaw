#!/usr/bin/env python3
"""Tests for rayvault/agent/jobs.py — job executor pure functions."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rayvault.agent.jobs import (
    JobArtifact,
    JobExecutionError,
    _artifact,
    _ffmpeg_exists,
    _has_active_ui_session,
    _safe_output_dir,
    _sha256_file,
    detect_capabilities,
)


# ---------------------------------------------------------------
# JobExecutionError
# ---------------------------------------------------------------

class TestJobExecutionError(unittest.TestCase):

    def test_fields(self):
        e = JobExecutionError("INVALID_INPUT", "missing payload")
        self.assertEqual(e.code, "INVALID_INPUT")
        self.assertEqual(e.message, "missing payload")
        self.assertIsInstance(e, RuntimeError)

    def test_string(self):
        e = JobExecutionError("CODE", "msg")
        self.assertIn("msg", str(e))


# ---------------------------------------------------------------
# JobArtifact
# ---------------------------------------------------------------

class TestJobArtifact(unittest.TestCase):

    def test_fields(self):
        a = JobArtifact(path="/tmp/f.txt", sha256="abc", size_bytes=100)
        self.assertEqual(a.path, "/tmp/f.txt")
        self.assertEqual(a.sha256, "abc")
        self.assertEqual(a.size_bytes, 100)


# ---------------------------------------------------------------
# _sha256_file
# ---------------------------------------------------------------

class TestSha256File(unittest.TestCase):

    def test_deterministic(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello world")
            p = Path(f.name)
        try:
            h1 = _sha256_file(p)
            h2 = _sha256_file(p)
            self.assertEqual(h1, h2)
            self.assertEqual(len(h1), 64)
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
            self.assertNotEqual(_sha256_file(p1), _sha256_file(p2))
        finally:
            p1.unlink()
            p2.unlink()


# ---------------------------------------------------------------
# _artifact
# ---------------------------------------------------------------

class TestArtifact(unittest.TestCase):

    def test_creates_artifact(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test data")
            p = Path(f.name)
        try:
            a = _artifact(p)
            self.assertEqual(a.path, str(p))
            self.assertEqual(len(a.sha256), 64)
            self.assertEqual(a.size_bytes, 9)
        finally:
            p.unlink()


# ---------------------------------------------------------------
# _safe_output_dir
# ---------------------------------------------------------------

class TestSafeOutputDir(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        # Resolve to handle macOS /var -> /private/var symlink
        self.workspace = Path(self._tmpdir).resolve()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_default_rel(self):
        out = _safe_output_dir(self.workspace, {}, "artifacts/job1")
        self.assertTrue(out.exists())
        self.assertTrue(str(out).startswith(str(self.workspace)))

    def test_payload_override(self):
        out = _safe_output_dir(
            self.workspace, {"output_dir": "custom/path"}, "default"
        )
        self.assertTrue(out.exists())
        self.assertIn("custom", str(out))

    def test_escape_rejected(self):
        with self.assertRaises(JobExecutionError) as ctx:
            _safe_output_dir(
                self.workspace, {"output_dir": "../../etc"}, "default"
            )
        self.assertIn("escapes", ctx.exception.message)

    def test_absolute_stripped_to_relative(self):
        # /tmp/evil -> lstrip("/") -> "tmp/evil" -> within workspace
        out = _safe_output_dir(
            self.workspace, {"output_dir": "/tmp/evil"}, "default"
        )
        self.assertTrue(str(out).startswith(str(self.workspace)))


# ---------------------------------------------------------------
# _ffmpeg_exists
# ---------------------------------------------------------------

class TestFfmpegExists(unittest.TestCase):

    @patch("shutil.which")
    def test_both_present(self, mock_which):
        mock_which.return_value = "/usr/bin/ffmpeg"
        result = _ffmpeg_exists()
        self.assertTrue(result)

    @patch("shutil.which")
    def test_ffmpeg_missing(self, mock_which):
        def which_side(name):
            return "/usr/bin/ffprobe" if name == "ffprobe" else None
        mock_which.side_effect = which_side
        self.assertFalse(_ffmpeg_exists())

    @patch("shutil.which")
    def test_ffprobe_missing(self, mock_which):
        def which_side(name):
            return "/usr/bin/ffmpeg" if name == "ffmpeg" else None
        mock_which.side_effect = which_side
        self.assertFalse(_ffmpeg_exists())

    @patch("shutil.which", return_value=None)
    def test_both_missing(self, mock_which):
        self.assertFalse(_ffmpeg_exists())


# ---------------------------------------------------------------
# _has_active_ui_session
# ---------------------------------------------------------------

class TestHasActiveUiSession(unittest.TestCase):

    @patch("rayvault.agent.jobs.sys")
    def test_darwin_with_term_program(self, mock_sys):
        mock_sys.platform = "darwin"
        with patch.dict(os.environ, {"TERM_PROGRAM": "iTerm2"}, clear=False):
            result = _has_active_ui_session()
            self.assertTrue(result)

    @patch("rayvault.agent.jobs.sys")
    def test_darwin_no_display(self, mock_sys):
        mock_sys.platform = "darwin"
        env = dict(os.environ)
        env.pop("DISPLAY", None)
        env.pop("TERM_PROGRAM", None)
        with patch.dict(os.environ, env, clear=True):
            result = _has_active_ui_session()
            self.assertFalse(result)

    @patch("rayvault.agent.jobs.sys")
    def test_linux_with_display(self, mock_sys):
        mock_sys.platform = "linux"
        with patch.dict(os.environ, {"DISPLAY": ":0"}, clear=False):
            result = _has_active_ui_session()
            self.assertTrue(result)

    @patch("rayvault.agent.jobs.sys")
    def test_linux_with_wayland(self, mock_sys):
        mock_sys.platform = "linux"
        env = dict(os.environ)
        env.pop("DISPLAY", None)
        env["WAYLAND_DISPLAY"] = "wayland-0"
        with patch.dict(os.environ, env, clear=True):
            result = _has_active_ui_session()
            self.assertTrue(result)


# ---------------------------------------------------------------
# detect_capabilities
# ---------------------------------------------------------------

class TestDetectCapabilities(unittest.TestCase):

    def test_returns_dict(self):
        caps = detect_capabilities()
        self.assertIsInstance(caps, dict)

    def test_has_platform(self):
        caps = detect_capabilities()
        self.assertEqual(caps["platform"], sys.platform)

    def test_has_python_version(self):
        caps = detect_capabilities()
        self.assertIn(".", caps["python"])

    def test_has_ffmpeg_key(self):
        caps = detect_capabilities()
        self.assertIn("ffmpeg", caps)
        self.assertIsInstance(caps["ffmpeg"], bool)

    def test_has_tts_provider(self):
        caps = detect_capabilities()
        self.assertIn("tts_provider", caps)

    def test_has_ui_session_key(self):
        caps = detect_capabilities()
        self.assertIn("ui_session_active", caps)
        self.assertIsInstance(caps["ui_session_active"], bool)

    def test_has_contract_capability_keys(self):
        caps = detect_capabilities()
        for key in (
            "os",
            "cpu",
            "ram_gb",
            "gpu_model",
            "vram_gb",
            "python_version",
            "ffmpeg_version",
            "davinci_available",
        ):
            self.assertIn(key, caps)


# ---------------------------------------------------------------
# _sha256_file edge cases
# ---------------------------------------------------------------

class TestSha256FileEdgeCases(unittest.TestCase):

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            p = Path(f.name)
        try:
            h = _sha256_file(p)
            self.assertEqual(len(h), 64)
            # SHA-256 of empty = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
            self.assertEqual(h, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
        finally:
            p.unlink()

    def test_known_hash(self):
        import hashlib
        content = b"test content for hash"
        expected = hashlib.sha256(content).hexdigest()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            p = Path(f.name)
        try:
            self.assertEqual(_sha256_file(p), expected)
        finally:
            p.unlink()


# ---------------------------------------------------------------
# _safe_output_dir edge cases
# ---------------------------------------------------------------

class TestSafeOutputDirEdgeCases(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.workspace = Path(self._tmpdir).resolve()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_empty_string_uses_default(self):
        out = _safe_output_dir(self.workspace, {"output_dir": ""}, "fallback")
        self.assertIn("fallback", str(out))

    def test_whitespace_only_uses_default(self):
        out = _safe_output_dir(self.workspace, {"output_dir": "   "}, "fallback")
        self.assertIn("fallback", str(out))

    def test_creates_nested_dirs(self):
        out = _safe_output_dir(
            self.workspace, {"output_dir": "a/b/c/d"}, "default"
        )
        self.assertTrue(out.exists())
        self.assertTrue(out.is_dir())

    def test_workspace_itself_valid(self):
        out = _safe_output_dir(self.workspace, {"output_dir": "."}, "default")
        self.assertEqual(out, self.workspace)


if __name__ == "__main__":
    unittest.main()
