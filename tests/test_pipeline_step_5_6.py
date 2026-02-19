#!/usr/bin/env python3
"""Tests for pipeline_step_5_render_upload.py and pipeline_step_6_collect_metrics.py."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from pipeline_step_5_render_upload import check_render_ready, upload_to_youtube
from pipeline_step_6_collect_metrics import extract_video_id, load_youtube_api_key


# ---------------------------------------------------------------
# Step 5: check_render_ready
# ---------------------------------------------------------------

class TestCheckRenderReady(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "run_001"
        self.run_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_true_when_flag_exists(self):
        (self.run_dir / "render_ready.flag").write_text("ready", encoding="utf-8")
        self.assertTrue(check_render_ready(self.run_dir))

    def test_false_when_no_flag(self):
        self.assertFalse(check_render_ready(self.run_dir))


# ---------------------------------------------------------------
# Step 5: upload_to_youtube
# ---------------------------------------------------------------

class TestUploadToYoutube(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "run_001"
        self.run_dir.mkdir()
        # Create mock video
        self.video_path = self.run_dir / "render_output" / "final.mp4"
        self.video_path.parent.mkdir(parents=True, exist_ok=True)
        self.video_path.write_bytes(b"fake mp4")
        # Create script.json
        self.script = {
            "video_title": "Top 5 Best Widgets",
            "segments": [{"type": "HOOK", "narration": "Hello"}],
            "youtube": {
                "description": "Top 5 widgets reviewed.",
                "tags": ["widgets", "review", "top 5"],
                "chapters": [
                    {"time": "0:00", "label": "Intro"},
                    {"time": "1:30", "label": "Product 1"},
                ],
            },
        }
        (self.run_dir / "script.json").write_text(
            json.dumps(self.script), encoding="utf-8"
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_returns_none_without_youtube_env(self):
        with patch("os.path.expanduser", return_value="/nonexistent/youtube.env"):
            result = upload_to_youtube(self.run_dir, self.video_path)
        self.assertIsNone(result)

    def test_creates_payload_json(self):
        with patch("os.path.expanduser", return_value="/nonexistent/youtube.env"):
            upload_to_youtube(self.run_dir, self.video_path)
        payload_path = self.run_dir / "youtube_upload_payload.json"
        self.assertTrue(payload_path.exists())

    def test_payload_has_correct_title(self):
        with patch("os.path.expanduser", return_value="/nonexistent/youtube.env"):
            upload_to_youtube(self.run_dir, self.video_path)
        payload = json.loads(
            (self.run_dir / "youtube_upload_payload.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["title"], "Top 5 Best Widgets")

    def test_payload_has_tags(self):
        with patch("os.path.expanduser", return_value="/nonexistent/youtube.env"):
            upload_to_youtube(self.run_dir, self.video_path)
        payload = json.loads(
            (self.run_dir / "youtube_upload_payload.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["tags"], ["widgets", "review", "top 5"])

    def test_payload_has_chapters_in_description(self):
        with patch("os.path.expanduser", return_value="/nonexistent/youtube.env"):
            upload_to_youtube(self.run_dir, self.video_path)
        payload = json.loads(
            (self.run_dir / "youtube_upload_payload.json").read_text(encoding="utf-8")
        )
        self.assertIn("0:00 Intro", payload["description"])
        self.assertIn("1:30 Product 1", payload["description"])

    def test_payload_privacy_is_private(self):
        with patch("os.path.expanduser", return_value="/nonexistent/youtube.env"):
            upload_to_youtube(self.run_dir, self.video_path)
        payload = json.loads(
            (self.run_dir / "youtube_upload_payload.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["privacy_status"], "private")

    def test_returns_none_when_no_script(self):
        (self.run_dir / "script.json").unlink()
        result = upload_to_youtube(self.run_dir, self.video_path)
        self.assertIsNone(result)

    def test_payload_video_file_path(self):
        with patch("os.path.expanduser", return_value="/nonexistent/youtube.env"):
            upload_to_youtube(self.run_dir, self.video_path)
        payload = json.loads(
            (self.run_dir / "youtube_upload_payload.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["video_file"], str(self.video_path))


# ---------------------------------------------------------------
# Step 5: main() CLI
# ---------------------------------------------------------------

class TestStep5Main(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "run_001"
        self.run_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_skip_if_url_exists(self):
        (self.run_dir / "youtube_url.txt").write_text("https://youtube.com/watch?v=abc", encoding="utf-8")
        (self.run_dir / "render_ready.flag").write_text("ready", encoding="utf-8")
        from pipeline_step_5_render_upload import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)

    def test_error_if_no_flag(self):
        from pipeline_step_5_render_upload import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)


# ---------------------------------------------------------------
# Step 6: extract_video_id
# ---------------------------------------------------------------

class TestExtractVideoId(unittest.TestCase):

    def test_youtube_com_standard(self):
        self.assertEqual(
            extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )

    def test_youtube_com_with_params(self):
        self.assertEqual(
            extract_video_id("https://www.youtube.com/watch?v=abc123&t=30s"),
            "abc123",
        )

    def test_youtu_be_short(self):
        self.assertEqual(extract_video_id("https://youtu.be/dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_invalid_url(self):
        self.assertEqual(extract_video_id("https://example.com/foo"), "")

    def test_empty_string(self):
        self.assertEqual(extract_video_id(""), "")

    def test_no_v_param(self):
        self.assertEqual(extract_video_id("https://www.youtube.com/watch"), "")


# ---------------------------------------------------------------
# Step 6: load_youtube_api_key
# ---------------------------------------------------------------

class TestLoadYoutubeApiKey(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_returns_key_from_file(self):
        env_file = Path(self.tmpdir) / "youtube.env"
        env_file.write_text("YOUTUBE_API_KEY=my_test_key_123\n", encoding="utf-8")
        with patch("pipeline_step_6_collect_metrics.os.path.expanduser", return_value=str(env_file)):
            key = load_youtube_api_key()
        self.assertEqual(key, "my_test_key_123")

    def test_returns_empty_when_no_file(self):
        with patch("pipeline_step_6_collect_metrics.os.path.expanduser",
                    return_value="/nonexistent/youtube.env"):
            key = load_youtube_api_key()
        self.assertEqual(key, "")

    def test_returns_empty_when_no_key_line(self):
        env_file = Path(self.tmpdir) / "youtube.env"
        env_file.write_text("OTHER_VAR=foo\n", encoding="utf-8")
        with patch("pipeline_step_6_collect_metrics.os.path.expanduser", return_value=str(env_file)):
            key = load_youtube_api_key()
        self.assertEqual(key, "")


# ---------------------------------------------------------------
# Step 6: main() CLI
# ---------------------------------------------------------------

class TestStep6Main(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "run_001"
        self.run_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_skip_if_metrics_exist(self):
        (self.run_dir / "metrics.json").write_text("{}", encoding="utf-8")
        from pipeline_step_6_collect_metrics import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)

    def test_error_if_no_url(self):
        from pipeline_step_6_collect_metrics import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_error_if_no_api_key(self):
        (self.run_dir / "youtube_url.txt").write_text(
            "https://www.youtube.com/watch?v=test123", encoding="utf-8"
        )
        from pipeline_step_6_collect_metrics import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with patch("pipeline_step_6_collect_metrics.load_youtube_api_key", return_value=""):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_error_if_invalid_url(self):
        (self.run_dir / "youtube_url.txt").write_text(
            "not-a-youtube-url", encoding="utf-8"
        )
        from pipeline_step_6_collect_metrics import main
        with patch("sys.argv", ["prog", "--run-dir", str(self.run_dir)]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)


# ---------------------------------------------------------------
# Step 5: upload_to_youtube — edge cases
# ---------------------------------------------------------------

class TestUploadToYoutubeEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "run_002"
        self.run_dir.mkdir()
        self.video_path = self.run_dir / "render_output" / "final.mp4"
        self.video_path.parent.mkdir(parents=True, exist_ok=True)
        self.video_path.write_bytes(b"fake mp4")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_script_without_youtube_key(self):
        script = {"video_title": "Test Video", "segments": []}
        (self.run_dir / "script.json").write_text(json.dumps(script), encoding="utf-8")
        with patch("os.path.expanduser", return_value="/nonexistent/youtube.env"):
            result = upload_to_youtube(self.run_dir, self.video_path)
        self.assertIsNone(result)
        payload_path = self.run_dir / "youtube_upload_payload.json"
        self.assertTrue(payload_path.exists())
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["title"], "Test Video")
        self.assertEqual(payload["tags"], [])

    def test_script_with_empty_chapters(self):
        script = {
            "video_title": "Test",
            "segments": [],
            "youtube": {"description": "desc", "tags": ["a"], "chapters": []},
        }
        (self.run_dir / "script.json").write_text(json.dumps(script), encoding="utf-8")
        with patch("os.path.expanduser", return_value="/nonexistent/youtube.env"):
            upload_to_youtube(self.run_dir, self.video_path)
        payload = json.loads(
            (self.run_dir / "youtube_upload_payload.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("0:00", payload.get("description", ""))

    def test_script_with_unicode_title(self):
        script = {
            "video_title": "Top 5 Fones — Melhor Custo Benefício 2026",
            "segments": [],
            "youtube": {"description": "análise", "tags": ["fone"]},
        }
        (self.run_dir / "script.json").write_text(json.dumps(script), encoding="utf-8")
        with patch("os.path.expanduser", return_value="/nonexistent/youtube.env"):
            upload_to_youtube(self.run_dir, self.video_path)
        payload = json.loads(
            (self.run_dir / "youtube_upload_payload.json").read_text(encoding="utf-8")
        )
        self.assertIn("Fones", payload["title"])


# ---------------------------------------------------------------
# Step 5: check_render_ready — edge cases
# ---------------------------------------------------------------

class TestCheckRenderReadyEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "run_003"
        self.run_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_flag_file(self):
        (self.run_dir / "render_ready.flag").write_text("", encoding="utf-8")
        self.assertTrue(check_render_ready(self.run_dir))

    def test_nonexistent_dir(self):
        self.assertFalse(check_render_ready(Path("/nonexistent/run")))


# ---------------------------------------------------------------
# Step 6: extract_video_id — edge cases
# ---------------------------------------------------------------

class TestExtractVideoIdEdgeCases(unittest.TestCase):

    def test_none_url(self):
        self.assertEqual(extract_video_id(None), "")

    def test_youtube_music_url(self):
        result = extract_video_id("https://music.youtube.com/watch?v=music1")
        self.assertEqual(result, "music1")

    def test_mobile_youtube(self):
        result = extract_video_id("https://m.youtube.com/watch?v=mob1")
        self.assertEqual(result, "mob1")

    def test_youtu_be_with_query(self):
        result = extract_video_id("https://youtu.be/abc?t=30")
        self.assertIn("abc", result)


if __name__ == "__main__":
    unittest.main()
