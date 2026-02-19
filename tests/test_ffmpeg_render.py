#!/usr/bin/env python3
"""Tests for rayvault/ffmpeg_render.py — segmented render engine pure functions."""

from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from rayvault.ffmpeg_render import (
    DURATION_TOLERANCE_SEC,
    FRAME_TOLERANCE,
    KENBURNS_UPSCALE_W,
    KENBURNS_ZOOM_FACTOR,
    MIN_STABILITY_SCORE,
    GateResult,
    RenderResult,
    SegmentResult,
    _scale_pad_filter,
    build_segment_cmd,
    classify_ffmpeg_error,
    compute_global_inputs_hash,
    compute_segment_inputs_hash,
    file_stat_sig,
    gate_essential_files,
    gate_frames_consistency,
    gate_overlay_refs,
    gate_segment_sources,
    gate_temporal_consistency,
    read_json,
    sha1_file,
    sha1_text,
    utc_now_iso,
    validate_run_inputs,
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

    def test_kenburns_zoom(self):
        self.assertEqual(KENBURNS_ZOOM_FACTOR, 1.08)

    def test_kenburns_upscale(self):
        self.assertEqual(KENBURNS_UPSCALE_W, 4000)

    def test_duration_tolerance(self):
        self.assertEqual(DURATION_TOLERANCE_SEC, 0.1)

    def test_frame_tolerance(self):
        self.assertEqual(FRAME_TOLERANCE, 2)

    def test_min_stability_score(self):
        self.assertEqual(MIN_STABILITY_SCORE, 0)


# ---------------------------------------------------------------
# utc_now_iso
# ---------------------------------------------------------------

class TestUtcNowIso(unittest.TestCase):

    def test_format(self):
        ts = utc_now_iso()
        self.assertTrue(ts.endswith("Z"))
        self.assertIn("T", ts)
        self.assertEqual(len(ts), 20)  # "YYYY-MM-DDTHH:MM:SSZ"


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


# ---------------------------------------------------------------
# wav_duration_seconds
# ---------------------------------------------------------------

class TestWavDurationSeconds(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_valid_wav(self):
        p = _make_wav(Path(self._tmpdir) / "test.wav", duration=2.5)
        dur = wav_duration_seconds(p)
        self.assertIsNotNone(dur)
        self.assertAlmostEqual(dur, 2.5, places=1)

    def test_nonexistent(self):
        self.assertIsNone(wav_duration_seconds(Path("/nonexistent.wav")))

    def test_invalid_file(self):
        p = Path(self._tmpdir) / "bad.wav"
        p.write_bytes(b"not a wav file")
        self.assertIsNone(wav_duration_seconds(p))


# ---------------------------------------------------------------
# read_json
# ---------------------------------------------------------------

class TestReadJson(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_valid(self):
        p = Path(self._tmpdir) / "data.json"
        p.write_text('{"key": "value"}', encoding="utf-8")
        self.assertEqual(read_json(p), {"key": "value"})

    def test_missing(self):
        with self.assertRaises(FileNotFoundError):
            read_json(Path("/nonexistent.json"))


# ---------------------------------------------------------------
# file_stat_sig
# ---------------------------------------------------------------

class TestFileStatSig(unittest.TestCase):

    def test_existing_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"data")
            p = Path(f.name)
        try:
            sig = file_stat_sig(p)
            self.assertIn(":", sig)
            size_str = sig.split(":")[0]
            self.assertEqual(int(size_str), 4)  # 4 bytes
        finally:
            p.unlink()

    def test_missing(self):
        self.assertEqual(file_stat_sig(Path("/nonexistent")), "missing")


# ---------------------------------------------------------------
# classify_ffmpeg_error
# ---------------------------------------------------------------

class TestClassifyFfmpegError(unittest.TestCase):

    def test_missing_input(self):
        self.assertEqual(
            classify_ffmpeg_error("No such file or directory"),
            "MISSING_INPUT",
        )

    def test_corrupt_media(self):
        self.assertEqual(
            classify_ffmpeg_error("Invalid data found when processing input"),
            "CORRUPT_MEDIA",
        )

    def test_oom(self):
        self.assertEqual(
            classify_ffmpeg_error("Cannot allocate memory"),
            "OOM",
        )

    def test_unknown_encoder(self):
        self.assertEqual(
            classify_ffmpeg_error("Unknown encoder libx999"),
            "FFMPEG_BUILD_MISSING",
        )

    def test_permission_denied(self):
        self.assertEqual(
            classify_ffmpeg_error("Permission denied"),
            "PERMISSION_DENIED",
        )

    def test_benign_id3_warning(self):
        # Benign warning pattern has empty code -> falls through to UNKNOWN
        self.assertEqual(
            classify_ffmpeg_error("Discarding ID3 tags"),
            "FFMPEG_UNKNOWN",
        )

    def test_unknown_error(self):
        self.assertEqual(
            classify_ffmpeg_error("some random error text"),
            "FFMPEG_UNKNOWN",
        )

    def test_empty_stderr(self):
        self.assertEqual(classify_ffmpeg_error(""), "FFMPEG_UNKNOWN")

    def test_corrupt_media_no_stream(self):
        self.assertEqual(
            classify_ffmpeg_error("does not contain any stream"),
            "CORRUPT_MEDIA",
        )

    def test_error_opening(self):
        self.assertEqual(
            classify_ffmpeg_error("Error opening input file foo.mp4"),
            "MISSING_INPUT",
        )


# ---------------------------------------------------------------
# GateResult
# ---------------------------------------------------------------

class TestGateResult(unittest.TestCase):

    def test_ok_defaults(self):
        r = GateResult(ok=True)
        self.assertTrue(r.ok)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.warnings, [])

    def test_fail_with_errors(self):
        r = GateResult(ok=False, errors=["ERR1"])
        self.assertFalse(r.ok)
        self.assertEqual(len(r.errors), 1)


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
        overlays = self.run_dir / "publish" / "overlays"
        overlays.mkdir(parents=True)
        (overlays / "overlays_index.json").write_text("{}")
        result = gate_essential_files(self.run_dir)
        self.assertTrue(result.ok)
        self.assertEqual(result.errors, [])

    def test_all_missing(self):
        result = gate_essential_files(self.run_dir)
        self.assertFalse(result.ok)
        self.assertEqual(len(result.errors), 4)

    def test_partial_missing(self):
        (self.run_dir / "00_manifest.json").write_text("{}")
        _make_wav(self.run_dir / "02_audio.wav")
        result = gate_essential_files(self.run_dir)
        self.assertFalse(result.ok)
        self.assertEqual(len(result.errors), 2)  # render_config + overlays


# ---------------------------------------------------------------
# gate_temporal_consistency
# ---------------------------------------------------------------

class TestGateTemporalConsistency(unittest.TestCase):

    def test_matching_duration(self):
        config = {"segments": [{"t0": 0, "t1": 10.0}]}
        result = gate_temporal_consistency(config, 10.0)
        self.assertTrue(result.ok)
        self.assertEqual(result.errors, [])

    def test_within_tolerance(self):
        config = {"segments": [{"t0": 0, "t1": 10.05}]}
        result = gate_temporal_consistency(config, 10.0)
        self.assertTrue(result.ok)

    def test_timeline_exceeds_audio(self):
        config = {"segments": [{"t0": 0, "t1": 12.0}]}
        result = gate_temporal_consistency(config, 10.0)
        self.assertFalse(result.ok)
        self.assertIn("TIMELINE_EXCEEDS_AUDIO", result.errors[0])

    def test_audio_tail_warning(self):
        config = {"segments": [{"t0": 0, "t1": 10.0}]}
        result = gate_temporal_consistency(config, 12.0)
        self.assertTrue(result.ok)  # warning only, not error
        self.assertGreater(len(result.warnings), 0)
        self.assertIn("AUDIO_TAIL", result.warnings[0])

    def test_no_segments(self):
        result = gate_temporal_consistency({}, 10.0)
        self.assertFalse(result.ok)
        self.assertIn("no segments", result.errors[0])

    def test_empty_segments(self):
        result = gate_temporal_consistency({"segments": []}, 10.0)
        self.assertFalse(result.ok)


# ---------------------------------------------------------------
# gate_frames_consistency
# ---------------------------------------------------------------

class TestGateFramesConsistency(unittest.TestCase):

    def test_correct_frames(self):
        # 2s at 30fps = 60 frames
        config = {
            "output": {"fps": 30},
            "segments": [{"t0": 0, "t1": 2.0, "frames": 60, "id": "s1"}],
        }
        result = gate_frames_consistency(config)
        self.assertTrue(result.ok)

    def test_within_tolerance(self):
        config = {
            "output": {"fps": 30},
            "segments": [{"t0": 0, "t1": 2.0, "frames": 61, "id": "s1"}],
        }
        result = gate_frames_consistency(config)
        self.assertTrue(result.ok)  # within FRAME_TOLERANCE=2

    def test_mismatch(self):
        config = {
            "output": {"fps": 30},
            "segments": [{"t0": 0, "t1": 2.0, "frames": 100, "id": "s1"}],
        }
        result = gate_frames_consistency(config)
        self.assertFalse(result.ok)
        self.assertIn("FRAME_MISMATCH", result.errors[0])

    def test_no_frames_field(self):
        # Backward compat: segments without frames field are skipped
        config = {
            "output": {"fps": 30},
            "segments": [{"t0": 0, "t1": 2.0, "id": "s1"}],
        }
        result = gate_frames_consistency(config)
        self.assertTrue(result.ok)

    def test_canvas_fallback(self):
        # If no output section, uses canvas
        config = {
            "canvas": {"fps": 24},
            "segments": [{"t0": 0, "t1": 1.0, "frames": 24, "id": "s1"}],
        }
        result = gate_frames_consistency(config)
        self.assertTrue(result.ok)

    def test_default_fps_30(self):
        # No output or canvas -> default fps 30
        config = {
            "segments": [{"t0": 0, "t1": 1.0, "frames": 30, "id": "s1"}],
        }
        result = gate_frames_consistency(config)
        self.assertTrue(result.ok)


# ---------------------------------------------------------------
# gate_segment_sources
# ---------------------------------------------------------------

class TestGateSegmentSources(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self._tmpdir) / "run"
        self.run_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_intro_with_frame(self):
        (self.run_dir / "03_frame.png").write_bytes(b"\x89PNG")
        config = {
            "ray": {},
            "segments": [{"type": "intro", "id": "intro"}],
        }
        result = gate_segment_sources(self.run_dir, config)
        self.assertTrue(result.ok)

    def test_intro_no_frame(self):
        config = {
            "ray": {},
            "segments": [{"type": "intro", "id": "intro"}],
        }
        result = gate_segment_sources(self.run_dir, config)
        self.assertFalse(result.ok)

    def test_skip_mode(self):
        config = {
            "ray": {},
            "segments": [{"type": "product", "visual": {"mode": "SKIP"}, "id": "p1"}],
        }
        result = gate_segment_sources(self.run_dir, config)
        self.assertTrue(result.ok)

    def test_source_missing(self):
        config = {
            "ray": {},
            "segments": [{
                "type": "product",
                "visual": {"mode": "KEN_BURNS", "source": "images/p1.jpg"},
                "id": "p1",
            }],
        }
        result = gate_segment_sources(self.run_dir, config)
        self.assertFalse(result.ok)
        self.assertIn("MISSING_SOURCE", result.errors[0])

    def test_source_exists(self):
        img = self.run_dir / "images"
        img.mkdir()
        (img / "p1.jpg").write_bytes(b"\xff\xd8\xff")
        config = {
            "ray": {},
            "segments": [{
                "type": "product",
                "visual": {"mode": "KEN_BURNS", "source": "images/p1.jpg"},
                "id": "p1",
            }],
        }
        result = gate_segment_sources(self.run_dir, config)
        self.assertTrue(result.ok)

    def test_no_source_path(self):
        config = {
            "ray": {},
            "segments": [{
                "type": "product",
                "visual": {"mode": "KEN_BURNS"},
                "id": "p1",
            }],
        }
        result = gate_segment_sources(self.run_dir, config)
        self.assertFalse(result.ok)
        self.assertIn("no source", result.errors[0])


# ---------------------------------------------------------------
# gate_overlay_refs
# ---------------------------------------------------------------

class TestGateOverlayRefs(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self._tmpdir) / "run"
        self.run_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_no_items(self):
        result = gate_overlay_refs(self.run_dir, {"items": []})
        self.assertTrue(result.ok)
        self.assertEqual(result.warnings, [])

    def test_hidden_item_skipped(self):
        idx = {"items": [{"display_mode": "HIDE", "rank": 1}]}
        result = gate_overlay_refs(self.run_dir, idx)
        self.assertTrue(result.ok)

    def test_missing_overlay(self):
        idx = {"items": [{
            "rank": 1,
            "lowerthird_path": "publish/overlays/lt_001.png",
        }]}
        result = gate_overlay_refs(self.run_dir, idx)
        self.assertTrue(result.ok)  # ok=True with warnings
        self.assertGreater(len(result.warnings), 0)
        self.assertIn("OVERLAY_MISSING", result.warnings[0])

    def test_overlay_present(self):
        ov = self.run_dir / "publish" / "overlays"
        ov.mkdir(parents=True)
        (ov / "lt_001.png").write_bytes(b"\x89PNG")
        idx = {"items": [{
            "rank": 1,
            "lowerthird_path": "publish/overlays/lt_001.png",
        }]}
        result = gate_overlay_refs(self.run_dir, idx)
        self.assertTrue(result.ok)
        self.assertEqual(result.warnings, [])


# ---------------------------------------------------------------
# validate_run_inputs (combined gates)
# ---------------------------------------------------------------

class TestValidateRunInputs(unittest.TestCase):

    def test_valid(self):
        tmpdir = tempfile.mkdtemp()
        try:
            run_dir = Path(tmpdir) / "run"
            run_dir.mkdir()
            (run_dir / "03_frame.png").write_bytes(b"\x89PNG")

            config = {
                "output": {"fps": 30},
                "segments": [
                    {"type": "intro", "t0": 0, "t1": 5.0, "id": "intro"},
                ],
            }
            overlays = {"items": []}
            manifest = {"products": {"stability_score_products": 100}}
            result = validate_run_inputs(run_dir, config, overlays, 5.0, manifest)
            self.assertTrue(result.ok)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_combined_errors(self):
        tmpdir = tempfile.mkdtemp()
        try:
            run_dir = Path(tmpdir) / "run"
            run_dir.mkdir()

            config = {
                "output": {"fps": 30},
                "segments": [
                    {"type": "product", "t0": 0, "t1": 50.0, "id": "p1",
                     "visual": {"mode": "KEN_BURNS"}, "frames": 999},
                ],
            }
            overlays = {"items": []}
            manifest = {}
            result = validate_run_inputs(run_dir, config, overlays, 10.0, manifest)
            self.assertFalse(result.ok)
            # Should have temporal error + frames error + missing source
            self.assertGreater(len(result.errors), 1)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------
# compute_segment_inputs_hash
# ---------------------------------------------------------------

class TestComputeSegmentInputsHash(unittest.TestCase):

    def test_deterministic(self):
        seg = {"id": "s1", "t0": 0, "t1": 5.0, "visual": {"mode": "SKIP"}}
        settings = {"w": 1920, "h": 1080, "fps": 30}
        h1 = compute_segment_inputs_hash(seg, Path("/tmp"), {}, settings)
        h2 = compute_segment_inputs_hash(seg, Path("/tmp"), {}, settings)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 40)

    def test_different_settings(self):
        seg = {"id": "s1", "t0": 0, "t1": 5.0, "visual": {"mode": "SKIP"}}
        h1 = compute_segment_inputs_hash(
            seg, Path("/tmp"), {}, {"w": 1920, "h": 1080, "fps": 30},
        )
        h2 = compute_segment_inputs_hash(
            seg, Path("/tmp"), {}, {"w": 1280, "h": 720, "fps": 30},
        )
        self.assertNotEqual(h1, h2)

    def test_with_source_file(self):
        tmpdir = tempfile.mkdtemp()
        try:
            run_dir = Path(tmpdir) / "run"
            run_dir.mkdir()
            src = run_dir / "img.jpg"
            src.write_bytes(b"\xff\xd8\xff")
            seg = {"id": "s1", "t0": 0, "t1": 5.0,
                   "visual": {"mode": "KEN_BURNS", "source": "img.jpg"}}
            settings = {"w": 1920, "h": 1080, "fps": 30}
            h = compute_segment_inputs_hash(seg, run_dir, {}, settings)
            self.assertEqual(len(h), 40)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------
# compute_global_inputs_hash
# ---------------------------------------------------------------

class TestComputeGlobalInputsHash(unittest.TestCase):

    def test_deterministic(self):
        tmpdir = tempfile.mkdtemp()
        try:
            run_dir = Path(tmpdir)
            rc = run_dir / "config.json"
            rc.write_text("{}", encoding="utf-8")
            audio = run_dir / "audio.wav"
            _make_wav(audio, duration=1.0)
            ov = run_dir / "overlays.json"
            ov.write_text("{}", encoding="utf-8")

            h1 = compute_global_inputs_hash(rc, audio, ov, ["aaa", "bbb"])
            h2 = compute_global_inputs_hash(rc, audio, ov, ["aaa", "bbb"])
            self.assertEqual(h1, h2)
            self.assertEqual(len(h1), 40)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_different_segment_hashes(self):
        tmpdir = tempfile.mkdtemp()
        try:
            run_dir = Path(tmpdir)
            rc = run_dir / "config.json"
            rc.write_text("{}", encoding="utf-8")
            audio = run_dir / "audio.wav"
            _make_wav(audio, duration=1.0)
            ov = run_dir / "overlays.json"
            ov.write_text("{}", encoding="utf-8")

            h1 = compute_global_inputs_hash(rc, audio, ov, ["aaa"])
            h2 = compute_global_inputs_hash(rc, audio, ov, ["bbb"])
            self.assertNotEqual(h1, h2)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------
# _scale_pad_filter
# ---------------------------------------------------------------

class TestScalePadFilter(unittest.TestCase):

    def test_1080p(self):
        f = _scale_pad_filter(1920, 1080)
        self.assertIn("1920", f)
        self.assertIn("1080", f)
        self.assertIn("scale=", f)
        self.assertIn("pad=", f)
        self.assertIn("setsar=1", f)

    def test_720p(self):
        f = _scale_pad_filter(1280, 720)
        self.assertIn("1280", f)
        self.assertIn("720", f)


# ---------------------------------------------------------------
# build_segment_cmd
# ---------------------------------------------------------------

class TestBuildSegmentCmd(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self._tmpdir) / "run"
        self.run_dir.mkdir()
        # Create standard frame
        (self.run_dir / "03_frame.png").write_bytes(b"\x89PNG")
        self._settings = {
            "w": 1920, "h": 1080, "fps": 30,
            "crf": 18, "preset": "slow", "pix_fmt": "yuv420p",
            "vcodec": "libx264",
        }

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_intro_cmd(self):
        seg = {"type": "intro", "t0": 0, "t1": 3.0, "id": "intro"}
        out = self.run_dir / "out.mp4"
        cmd = build_segment_cmd(seg, self.run_dir, self._settings, {"items": []}, out)
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("-loop", cmd)
        self.assertIn("1", cmd)
        self.assertIn(str(self.run_dir / "03_frame.png"), cmd)
        self.assertIn(str(out), cmd)

    def test_outro_cmd(self):
        seg = {"type": "outro", "t0": 10.0, "t1": 13.0, "id": "outro"}
        out = self.run_dir / "out.mp4"
        cmd = build_segment_cmd(seg, self.run_dir, self._settings, {"items": []}, out)
        self.assertIn("-loop", cmd)

    def test_skip_mode_black_frame(self):
        seg = {"type": "product", "t0": 0, "t1": 5.0,
               "visual": {"mode": "SKIP"}, "id": "p1"}
        out = self.run_dir / "out.mp4"
        cmd = build_segment_cmd(seg, self.run_dir, self._settings, {"items": []}, out)
        self.assertIn("-f", cmd)
        self.assertIn("lavfi", cmd)
        # Should include color=c=black
        cmd_str = " ".join(cmd)
        self.assertIn("color=c=black", cmd_str)

    def test_broll_video_cmd(self):
        src = self.run_dir / "broll.mp4"
        src.write_bytes(b"\x00\x00")
        seg = {"type": "product", "t0": 0, "t1": 5.0,
               "visual": {"mode": "BROLL_VIDEO", "source": "broll.mp4"},
               "id": "p1"}
        out = self.run_dir / "out.mp4"
        cmd = build_segment_cmd(seg, self.run_dir, self._settings, {"items": []}, out)
        self.assertIn("-stream_loop", cmd)
        self.assertIn(str(src), cmd)

    def test_ken_burns_cmd(self):
        src = self.run_dir / "img.jpg"
        src.write_bytes(b"\xff\xd8\xff")
        seg = {"type": "product", "t0": 0, "t1": 5.0, "frames": 150,
               "visual": {"mode": "KEN_BURNS", "source": "img.jpg"},
               "id": "p1"}
        out = self.run_dir / "out.mp4"
        cmd = build_segment_cmd(seg, self.run_dir, self._settings, {"items": []}, out)
        cmd_str = " ".join(cmd)
        self.assertIn("zoompan", cmd_str)
        self.assertIn(str(KENBURNS_UPSCALE_W), cmd_str)

    def test_still_only_cmd(self):
        src = self.run_dir / "img.jpg"
        src.write_bytes(b"\xff\xd8\xff")
        seg = {"type": "product", "t0": 0, "t1": 5.0,
               "visual": {"mode": "STILL_ONLY", "source": "img.jpg"},
               "id": "p1"}
        out = self.run_dir / "out.mp4"
        cmd = build_segment_cmd(seg, self.run_dir, self._settings, {"items": []}, out)
        self.assertIn("-loop", cmd)
        cmd_str = " ".join(cmd)
        self.assertNotIn("zoompan", cmd_str)

    def test_unknown_mode_fallback_black(self):
        seg = {"type": "product", "t0": 0, "t1": 5.0,
               "visual": {"mode": "UNKNOWN_FUTURE"},
               "id": "p1"}
        out = self.run_dir / "out.mp4"
        cmd = build_segment_cmd(seg, self.run_dir, self._settings, {"items": []}, out)
        cmd_str = " ".join(cmd)
        self.assertIn("color=c=black", cmd_str)

    def test_encoding_args(self):
        seg = {"type": "intro", "t0": 0, "t1": 1.0, "id": "intro"}
        out = self.run_dir / "out.mp4"
        cmd = build_segment_cmd(seg, self.run_dir, self._settings, {"items": []}, out)
        self.assertIn("-c:v", cmd)
        self.assertIn("libx264", cmd)
        self.assertIn("-crf", cmd)
        self.assertIn("18", cmd)
        self.assertIn("-an", cmd)  # no audio in segments

    def test_no_source_field_uses_skip(self):
        seg = {"type": "product", "t0": 0, "t1": 5.0,
               "visual": {"mode": "BROLL_VIDEO"},
               "id": "p1"}
        out = self.run_dir / "out.mp4"
        cmd = build_segment_cmd(seg, self.run_dir, self._settings, {"items": []}, out)
        cmd_str = " ".join(cmd)
        self.assertIn("color=c=black", cmd_str)

    def test_duration_from_t1_t0(self):
        seg = {"type": "intro", "t0": 5.0, "t1": 8.5, "id": "intro"}
        out = self.run_dir / "out.mp4"
        cmd = build_segment_cmd(seg, self.run_dir, self._settings, {"items": []}, out)
        # Duration should be 3.5
        self.assertIn("-t", cmd)
        idx = cmd.index("-t")
        self.assertEqual(cmd[idx + 1], "3.5")


# ---------------------------------------------------------------
# SegmentResult
# ---------------------------------------------------------------

class TestSegmentResult(unittest.TestCase):

    def test_defaults(self):
        r = SegmentResult(seg_id="s1", ok=True)
        self.assertFalse(r.cached)
        self.assertEqual(r.inputs_hash, "")
        self.assertIsNone(r.output_path)
        self.assertIsNone(r.output_sha1)
        self.assertEqual(r.duration_sec, 0.0)
        self.assertIsNone(r.error_code)
        self.assertEqual(r.warnings, [])

    def test_cached_segment(self):
        r = SegmentResult(
            seg_id="s1", ok=True, cached=True,
            inputs_hash="abc", output_path="/tmp/s1.mp4",
        )
        self.assertTrue(r.cached)
        self.assertEqual(r.inputs_hash, "abc")

    def test_failed_segment(self):
        r = SegmentResult(
            seg_id="s1", ok=False,
            error_code="TIMEOUT",
            warnings=["took too long"],
        )
        self.assertFalse(r.ok)
        self.assertEqual(r.error_code, "TIMEOUT")


# ---------------------------------------------------------------
# RenderResult
# ---------------------------------------------------------------

class TestRenderResult(unittest.TestCase):

    def test_defaults(self):
        r = RenderResult(ok=True)
        self.assertEqual(r.status, "UNKNOWN")
        self.assertEqual(r.segments_rendered, 0)
        self.assertEqual(r.segments_cached, 0)
        self.assertEqual(r.segments_total, 0)
        self.assertEqual(r.overlays_applied, 0)
        self.assertEqual(r.overlays_suppressed, 0)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.warnings, [])
        self.assertIsNone(r.patient_zero)

    def test_blocked(self):
        r = RenderResult(
            ok=False, status="BLOCKED",
            errors=["MISSING: 00_manifest.json"],
        )
        self.assertEqual(r.status, "BLOCKED")

    def test_rendered(self):
        r = RenderResult(
            ok=True, status="RENDERED",
            segments_rendered=5, segments_cached=3, segments_total=8,
            output_path="/tmp/video.mp4", output_bytes=5_000_000,
        )
        self.assertEqual(r.segments_total, 8)
        self.assertEqual(r.output_bytes, 5_000_000)


# ---------------------------------------------------------------
# build_segment_cmd with overlays
# ---------------------------------------------------------------

class TestBuildSegmentCmdWithOverlays(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self._tmpdir) / "run"
        self.run_dir.mkdir()
        (self.run_dir / "03_frame.png").write_bytes(b"\x89PNG")
        ov_dir = self.run_dir / "publish" / "overlays"
        ov_dir.mkdir(parents=True)
        (ov_dir / "lt_001.png").write_bytes(b"\x89PNG")
        (ov_dir / "qr_001.png").write_bytes(b"\x89PNG")
        self._settings = {
            "w": 1920, "h": 1080, "fps": 30,
            "crf": 18, "preset": "slow", "pix_fmt": "yuv420p",
            "vcodec": "libx264",
        }

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_intro_with_overlay(self):
        idx = {"items": [{
            "rank": 1,
            "lowerthird_path": "publish/overlays/lt_001.png",
            "coords": {"lowerthird": {"x": 100, "y": 800}},
        }]}
        seg = {"type": "intro", "t0": 0, "t1": 3.0, "id": "intro", "rank": 1}
        out = self.run_dir / "out.mp4"
        cmd = build_segment_cmd(seg, self.run_dir, self._settings, idx, out)
        cmd_str = " ".join(cmd)
        self.assertIn("overlay=", cmd_str)
        self.assertIn("filter_complex", cmd_str)

    def test_product_ken_burns_with_overlay(self):
        src = self.run_dir / "img.jpg"
        src.write_bytes(b"\xff\xd8\xff")
        idx = {"items": [{
            "rank": 2,
            "lowerthird_path": "publish/overlays/lt_001.png",
            "qr_path": "publish/overlays/qr_001.png",
            "coords": {
                "lowerthird": {"x": 100, "y": 800},
                "qr": {"x": 1700, "y": 800},
            },
        }]}
        seg = {"type": "product", "t0": 0, "t1": 5.0, "frames": 150,
               "visual": {"mode": "KEN_BURNS", "source": "img.jpg"},
               "rank": 2, "id": "p2"}
        out = self.run_dir / "out.mp4"
        cmd = build_segment_cmd(seg, self.run_dir, self._settings, idx, out)
        cmd_str = " ".join(cmd)
        self.assertIn("overlay=", cmd_str)
        self.assertIn("zoompan", cmd_str)


if __name__ == "__main__":
    unittest.main()
