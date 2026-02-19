#!/usr/bin/env python3
"""Tests for rayvault/davinci_assembler.py — pure functions and dataclasses."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import wave
from pathlib import Path

from rayvault.davinci_assembler import (
    GateResult,
    RS_FAILED_HARD,
    RS_RECOVERING,
    RS_RENDERED_OK,
    RS_STALLED,
    RS_STARTED,
    TEMPLATE_PROJECT_NAME,
    VerifyResult,
    check_disk_space,
    compute_inputs_hash,
    gate_essential_files,
    read_json,
    sha1_file,
    sha1_text,
    utc_now_iso,
    wav_duration_seconds,
)


# ---------------------------------------------------------------
# Helper: create minimal WAV file
# ---------------------------------------------------------------

def _make_wav(path: Path, duration: float = 1.0, rate: int = 44100) -> Path:
    n_frames = int(rate * duration)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * n_frames)
    return path


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

class TestConstants(unittest.TestCase):

    def test_render_states(self):
        self.assertEqual(RS_STARTED, "RENDER_STARTED")
        self.assertEqual(RS_STALLED, "RENDER_STALLED")
        self.assertEqual(RS_RECOVERING, "RENDER_RECOVERING")
        self.assertEqual(RS_FAILED_HARD, "RENDER_FAILED_HARD")
        self.assertEqual(RS_RENDERED_OK, "RENDERED_OK")

    def test_template_project_name(self):
        self.assertEqual(TEMPLATE_PROJECT_NAME, "RayVault_Template_v1")


# ---------------------------------------------------------------
# utc_now_iso
# ---------------------------------------------------------------

class TestUtcNowIso(unittest.TestCase):

    def test_format(self):
        ts = utc_now_iso()
        self.assertTrue(ts.endswith("Z"))
        self.assertIn("T", ts)
        self.assertEqual(len(ts), 20)


# ---------------------------------------------------------------
# sha1_text / sha1_file
# ---------------------------------------------------------------

class TestSha1(unittest.TestCase):

    def test_sha1_text_deterministic(self):
        self.assertEqual(sha1_text("hello"), sha1_text("hello"))
        self.assertEqual(len(sha1_text("test")), 40)

    def test_sha1_text_different(self):
        self.assertNotEqual(sha1_text("a"), sha1_text("b"))

    def test_sha1_file_deterministic(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test data")
            p = Path(f.name)
        try:
            self.assertEqual(sha1_file(p), sha1_file(p))
            expected = hashlib.sha1(b"test data").hexdigest()
            self.assertEqual(sha1_file(p), expected)
        finally:
            p.unlink()


# ---------------------------------------------------------------
# read_json
# ---------------------------------------------------------------

class TestReadJson(unittest.TestCase):

    def test_valid(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump({"key": 42}, f)
            p = Path(f.name)
        try:
            self.assertEqual(read_json(p)["key"], 42)
        finally:
            p.unlink()

    def test_missing(self):
        with self.assertRaises(FileNotFoundError):
            read_json(Path("/nonexistent.json"))


# ---------------------------------------------------------------
# wav_duration_seconds
# ---------------------------------------------------------------

class TestWavDuration(unittest.TestCase):

    def test_valid(self):
        with tempfile.TemporaryDirectory() as d:
            p = _make_wav(Path(d) / "test.wav", duration=3.0)
            dur = wav_duration_seconds(p)
            self.assertIsNotNone(dur)
            self.assertAlmostEqual(dur, 3.0, places=1)

    def test_nonexistent(self):
        self.assertIsNone(wav_duration_seconds(Path("/nonexistent.wav")))

    def test_bad_file(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"not a wav file")
            p = Path(f.name)
        try:
            self.assertIsNone(wav_duration_seconds(p))
        finally:
            p.unlink()


# ---------------------------------------------------------------
# GateResult
# ---------------------------------------------------------------

class TestGateResult(unittest.TestCase):

    def test_ok(self):
        r = GateResult(ok=True)
        self.assertTrue(r.ok)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.warnings, [])

    def test_fail(self):
        r = GateResult(ok=False, errors=["ERR1", "ERR2"])
        self.assertFalse(r.ok)
        self.assertEqual(len(r.errors), 2)


# ---------------------------------------------------------------
# gate_essential_files
# ---------------------------------------------------------------

class TestGateEssentialFiles(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self._tmpdir) / "run"
        self.run_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_all_present(self):
        (self.run_dir / "00_manifest.json").write_text("{}")
        (self.run_dir / "05_render_config.json").write_text("{}")
        _make_wav(self.run_dir / "02_audio.wav")
        ov = self.run_dir / "publish" / "overlays"
        ov.mkdir(parents=True)
        (ov / "overlays_index.json").write_text("{}")
        result = gate_essential_files(self.run_dir)
        self.assertTrue(result.ok)
        self.assertEqual(result.errors, [])

    def test_all_missing(self):
        result = gate_essential_files(self.run_dir)
        self.assertFalse(result.ok)
        self.assertEqual(len(result.errors), 4)

    def test_partial(self):
        (self.run_dir / "00_manifest.json").write_text("{}")
        result = gate_essential_files(self.run_dir)
        self.assertFalse(result.ok)
        self.assertEqual(len(result.errors), 3)


# ---------------------------------------------------------------
# check_disk_space
# ---------------------------------------------------------------

class TestCheckDiskSpace(unittest.TestCase):

    def test_current_dir_has_space(self):
        # Current dir should have some free space
        with tempfile.TemporaryDirectory() as d:
            result = check_disk_space(
                Path(d), estimated_output_gb=0.001, cache_dir=Path(d),
                min_cache_gb=0.001,
            )
            self.assertTrue(result["ok"])
            self.assertIsNotNone(result["export_free_gb"])
            self.assertGreater(result["export_free_gb"], 0)

    def test_nonexistent_cache_dir(self):
        with tempfile.TemporaryDirectory() as d:
            result = check_disk_space(
                Path(d), estimated_output_gb=0.001,
                cache_dir=Path("/nonexistent_cache_dir_xyz"),
                min_cache_gb=0.001,
            )
            self.assertIsNone(result["cache_free_gb"])

    def test_errors_list(self):
        with tempfile.TemporaryDirectory() as d:
            result = check_disk_space(Path(d))
            self.assertIsInstance(result["errors"], list)


# ---------------------------------------------------------------
# compute_inputs_hash
# ---------------------------------------------------------------

class TestComputeInputsHash(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self._tmpdir) / "run"
        self.run_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_deterministic(self):
        (self.run_dir / "05_render_config.json").write_text('{"fps": 30}')
        _make_wav(self.run_dir / "02_audio.wav")
        ov = self.run_dir / "publish" / "overlays"
        ov.mkdir(parents=True)
        (ov / "overlays_index.json").write_text("{}")

        h1 = compute_inputs_hash(self.run_dir)
        h2 = compute_inputs_hash(self.run_dir)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 40)

    def test_with_soundtrack(self):
        (self.run_dir / "05_render_config.json").write_text("{}")
        _make_wav(self.run_dir / "02_audio.wav")

        h1 = compute_inputs_hash(self.run_dir)
        h2 = compute_inputs_hash(self.run_dir, soundtrack_sha1="abc123")
        self.assertNotEqual(h1, h2)

    def test_engine_included(self):
        (self.run_dir / "05_render_config.json").write_text("{}")
        h = compute_inputs_hash(self.run_dir)
        self.assertEqual(len(h), 40)

    def test_missing_files_still_works(self):
        h = compute_inputs_hash(self.run_dir)
        self.assertEqual(len(h), 40)


# ---------------------------------------------------------------
# VerifyResult
# ---------------------------------------------------------------

class TestVerifyResult(unittest.TestCase):

    def test_defaults(self):
        r = VerifyResult(ok=True)
        self.assertEqual(r.duration_sec, 0.0)
        self.assertEqual(r.codec_video, "")
        self.assertEqual(r.codec_audio, "")
        self.assertEqual(r.fps, 0.0)
        self.assertIsNone(r.lufs_integrated)
        self.assertIsNone(r.true_peak)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.warnings, [])

    def test_failed(self):
        r = VerifyResult(ok=False, errors=["OUTPUT_MISSING"])
        self.assertFalse(r.ok)
        self.assertEqual(r.errors, ["OUTPUT_MISSING"])

    def test_with_metrics(self):
        r = VerifyResult(
            ok=True, duration_sec=45.5,
            codec_video="h264", codec_audio="aac",
            fps=30.0, lufs_integrated=-14.0, true_peak=-1.0,
        )
        self.assertEqual(r.duration_sec, 45.5)
        self.assertEqual(r.codec_video, "h264")
        self.assertEqual(r.lufs_integrated, -14.0)


if __name__ == "__main__":
    unittest.main()
