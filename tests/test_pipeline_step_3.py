#!/usr/bin/env python3
"""Tests for pipeline_step_3_generate_voice.py — voice segment file generation and manifest."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def _make_script(n_segments: int = 5) -> dict:
    """Build a minimal structured script with narration segments."""
    segments = [
        {"type": "HOOK", "narration": "Here is what you need to know about these products."},
        {"type": "CREDIBILITY", "narration": "I tested these for two weeks straight."},
    ]
    for i in range(n_segments):
        segments.append({
            "type": "PRODUCT_INTRO",
            "narration": f"Number {n_segments - i}. The Product {i + 1}.",
            "product_name": f"Product {i + 1}",
        })
    segments.append({
        "type": "ENDING_DECISION",
        "narration": "Check the links below for current pricing.",
    })
    return {
        "video_title": "Test Video",
        "segments": segments,
        "youtube": {"description": "", "tags": [], "chapters": []},
    }


class TestMainCLI(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "run_001"
        self.run_dir.mkdir()
        (self.run_dir / "script.json").write_text(
            json.dumps(_make_script(3)), encoding="utf-8"
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_main(self, extra_args=None):
        from pipeline_step_3_generate_voice import main
        argv = ["prog", "--run-dir", str(self.run_dir)]
        if extra_args:
            argv.extend(extra_args)
        with patch("sys.argv", argv):
            try:
                main()
            except SystemExit:
                pass

    def test_creates_voice_manifest(self):
        self._run_main()
        self.assertTrue((self.run_dir / "voice_manifest.json").exists())

    def test_creates_full_narration(self):
        self._run_main()
        self.assertTrue((self.run_dir / "full_narration.txt").exists())

    def test_creates_voice_segments_dir(self):
        self._run_main()
        self.assertTrue((self.run_dir / "voice_segments").is_dir())

    def test_segment_txt_files_created(self):
        self._run_main()
        txt_files = list((self.run_dir / "voice_segments").glob("*.txt"))
        self.assertGreater(len(txt_files), 0)

    def test_segment_count_matches(self):
        self._run_main()
        manifest = json.loads((self.run_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        # 2 structural + 3 products + 1 ending = 6 segments with narration
        self.assertEqual(manifest["total_segments"], 6)

    def test_manifest_has_required_keys(self):
        self._run_main()
        manifest = json.loads((self.run_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        for key in ("voice_name", "voice_settings", "total_segments", "total_words",
                     "estimated_duration_seconds", "segments", "ready_segments", "full_narration_file"):
            self.assertIn(key, manifest)

    def test_manifest_segments_have_fields(self):
        self._run_main()
        manifest = json.loads((self.run_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        seg = manifest["segments"][0]
        for key in ("segment_id", "type", "text_file", "audio_file", "audio_exists",
                     "word_count", "estimated_seconds"):
            self.assertIn(key, seg)

    def test_audio_not_ready_initially(self):
        self._run_main()
        manifest = json.loads((self.run_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["ready_segments"], 0)

    def test_total_words_positive(self):
        self._run_main()
        manifest = json.loads((self.run_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        self.assertGreater(manifest["total_words"], 0)

    def test_estimated_duration_positive(self):
        self._run_main()
        manifest = json.loads((self.run_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        self.assertGreater(manifest["estimated_duration_seconds"], 0)

    def test_full_narration_contains_all_text(self):
        self._run_main()
        narration = (self.run_dir / "full_narration.txt").read_text(encoding="utf-8")
        self.assertIn("Here is what you need to know", narration)
        self.assertIn("Check the links below", narration)

    def test_voice_name_default(self):
        self._run_main()
        manifest = json.loads((self.run_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["voice_name"], "Thomas Louis")

    def test_voice_name_custom(self):
        self._run_main(["--voice-name", "Custom Voice"])
        manifest = json.loads((self.run_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["voice_name"], "Custom Voice")

    def test_voice_settings_present(self):
        self._run_main()
        manifest = json.loads((self.run_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        settings = manifest["voice_settings"]
        self.assertIn("stability", settings)
        self.assertIn("similarity_boost", settings)

    def test_skip_if_manifest_exists(self):
        (self.run_dir / "voice_manifest.json").write_text("{}", encoding="utf-8")
        from pipeline_step_3_generate_voice import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)

    def test_error_if_no_script(self):
        (self.run_dir / "script.json").unlink()
        from pipeline_step_3_generate_voice import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_error_if_no_narration(self):
        script = {"video_title": "Test", "segments": [], "youtube": {}}
        (self.run_dir / "script.json").write_text(json.dumps(script), encoding="utf-8")
        from pipeline_step_3_generate_voice import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_segment_txt_content_matches_narration(self):
        self._run_main()
        manifest = json.loads((self.run_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        seg = manifest["segments"][0]
        txt_content = Path(seg["text_file"]).read_text(encoding="utf-8")
        self.assertIn("you need to know", txt_content)

    def test_manifest_is_valid_json(self):
        self._run_main()
        raw = (self.run_dir / "voice_manifest.json").read_text(encoding="utf-8")
        data = json.loads(raw)  # Should not raise
        self.assertIsInstance(data, dict)


# ---------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------

class TestStep3EdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "run_edge"
        self.run_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_main(self, extra_args=None):
        from pipeline_step_3_generate_voice import main
        argv = ["prog", "--run-dir", str(self.run_dir)]
        if extra_args:
            argv.extend(extra_args)
        with patch("sys.argv", argv):
            try:
                main()
            except SystemExit:
                pass

    def test_single_segment_script(self):
        script = {
            "video_title": "Test",
            "segments": [{"type": "HOOK", "narration": "A single hook."}],
            "youtube": {},
        }
        (self.run_dir / "script.json").write_text(json.dumps(script), encoding="utf-8")
        self._run_main()
        manifest = json.loads((self.run_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["total_segments"], 1)

    def test_many_segments_script(self):
        script = _make_script(10)
        (self.run_dir / "script.json").write_text(json.dumps(script), encoding="utf-8")
        self._run_main()
        manifest = json.loads((self.run_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["total_segments"], 13)  # 2+10+1

    def test_unicode_narration(self):
        script = {
            "video_title": "Test",
            "segments": [{"type": "HOOK", "narration": "Análise completa dos melhores fones."}],
            "youtube": {},
        }
        (self.run_dir / "script.json").write_text(json.dumps(script), encoding="utf-8")
        self._run_main()
        narration = (self.run_dir / "full_narration.txt").read_text(encoding="utf-8")
        self.assertIn("Análise", narration)

    def test_segments_without_narration_skipped(self):
        script = {
            "video_title": "Test",
            "segments": [
                {"type": "HOOK", "narration": "Hello"},
                {"type": "TRANSITION"},  # no narration
                {"type": "ENDING_DECISION", "narration": "Goodbye"},
            ],
            "youtube": {},
        }
        (self.run_dir / "script.json").write_text(json.dumps(script), encoding="utf-8")
        self._run_main()
        manifest = json.loads((self.run_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["total_segments"], 2)

    def test_long_narration_text(self):
        long_text = "word " * 500
        script = {
            "video_title": "Test",
            "segments": [{"type": "HOOK", "narration": long_text}],
            "youtube": {},
        }
        (self.run_dir / "script.json").write_text(json.dumps(script), encoding="utf-8")
        self._run_main()
        manifest = json.loads((self.run_dir / "voice_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["total_words"], 500)


if __name__ == "__main__":
    unittest.main()
