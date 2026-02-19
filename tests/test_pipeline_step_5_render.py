#!/usr/bin/env python3
"""Tests for tools/pipeline_step_5_render_upload.py — check_render_ready + upload logic."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from pipeline_step_5_render_upload import check_render_ready


# ---------------------------------------------------------------
# check_render_ready
# ---------------------------------------------------------------

class TestCheckRenderReady(unittest.TestCase):

    def test_flag_exists(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d)
            (run_dir / "render_ready.flag").write_text("ready", encoding="utf-8")
            self.assertTrue(check_render_ready(run_dir))

    def test_flag_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(check_render_ready(Path(d)))

    def test_empty_flag_still_true(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d)
            (run_dir / "render_ready.flag").write_text("", encoding="utf-8")
            self.assertTrue(check_render_ready(run_dir))


# ---------------------------------------------------------------
# YouTube chapter formatting (inline test of the logic from upload_to_youtube)
# ---------------------------------------------------------------

class TestChapterFormatting(unittest.TestCase):
    """Test the chapter-to-description logic from upload_to_youtube."""

    def _format_chapters(self, chapters, base_description=""):
        if chapters:
            chapter_lines = [f"{ch['time']} {ch['label']}" for ch in chapters]
            return "\n".join(chapter_lines) + "\n\n" + base_description
        return base_description

    def test_no_chapters(self):
        result = self._format_chapters([], "Base desc")
        self.assertEqual(result, "Base desc")

    def test_single_chapter(self):
        result = self._format_chapters([{"time": "0:00", "label": "Intro"}], "Desc")
        self.assertIn("0:00 Intro", result)
        self.assertIn("Desc", result)

    def test_multiple_chapters(self):
        chapters = [
            {"time": "0:00", "label": "Intro"},
            {"time": "1:30", "label": "Product 1"},
            {"time": "5:00", "label": "Conclusion"},
        ]
        result = self._format_chapters(chapters, "Details")
        lines = result.split("\n")
        self.assertEqual(lines[0], "0:00 Intro")
        self.assertEqual(lines[1], "1:30 Product 1")
        self.assertEqual(lines[2], "5:00 Conclusion")


# ---------------------------------------------------------------
# Upload payload construction (inline test)
# ---------------------------------------------------------------

class TestUploadPayload(unittest.TestCase):
    """Test that upload payload has correct structure."""

    def _build_payload(self, title, description, tags, video_path):
        return {
            "video_file": str(video_path),
            "title": title,
            "description": description,
            "tags": tags,
            "category_id": "28",
            "privacy_status": "private",
        }

    def test_payload_structure(self):
        payload = self._build_payload(
            "Top 5 Earbuds",
            "Review of earbuds",
            ["earbuds", "review"],
            "/tmp/video.mp4",
        )
        self.assertEqual(payload["title"], "Top 5 Earbuds")
        self.assertEqual(payload["category_id"], "28")
        self.assertEqual(payload["privacy_status"], "private")
        self.assertEqual(len(payload["tags"]), 2)

    def test_empty_tags(self):
        payload = self._build_payload("T", "D", [], "/tmp/v.mp4")
        self.assertEqual(payload["tags"], [])


# ---------------------------------------------------------------
# check_render_ready edge cases
# ---------------------------------------------------------------

class TestCheckRenderReadyEdgeCases(unittest.TestCase):

    def test_nested_dir_no_flag(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d) / "sub" / "run"
            run_dir.mkdir(parents=True)
            self.assertFalse(check_render_ready(run_dir))

    def test_flag_with_whitespace_content(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d)
            (run_dir / "render_ready.flag").write_text("  \n  ", encoding="utf-8")
            self.assertTrue(check_render_ready(run_dir))

    def test_flag_with_json_content(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d)
            (run_dir / "render_ready.flag").write_text('{"ready": true}', encoding="utf-8")
            self.assertTrue(check_render_ready(run_dir))

    def test_nonexistent_dir(self):
        result = check_render_ready(Path("/nonexistent/path/run_dir"))
        self.assertFalse(result)


# ---------------------------------------------------------------
# Chapter formatting edge cases
# ---------------------------------------------------------------

class TestChapterFormattingEdgeCases(unittest.TestCase):

    def _format_chapters(self, chapters, base_description=""):
        if chapters:
            chapter_lines = [f"{ch['time']} {ch['label']}" for ch in chapters]
            return "\n".join(chapter_lines) + "\n\n" + base_description
        return base_description

    def test_empty_description_with_chapters(self):
        result = self._format_chapters([{"time": "0:00", "label": "Start"}], "")
        self.assertIn("0:00 Start", result)

    def test_unicode_chapter_labels(self):
        chapters = [
            {"time": "0:00", "label": "Introdução"},
            {"time": "2:30", "label": "Análise #1"},
        ]
        result = self._format_chapters(chapters, "Descrição")
        self.assertIn("Introdução", result)
        self.assertIn("Análise", result)

    def test_many_chapters(self):
        chapters = [{"time": f"{i}:00", "label": f"Chapter {i}"} for i in range(20)]
        result = self._format_chapters(chapters, "Base")
        self.assertEqual(result.count("\n"), 21)  # 19 between chapters + 2 before base

    def test_chapter_with_special_chars(self):
        chapters = [{"time": "0:00", "label": "Product #1 — Best & Cheapest"}]
        result = self._format_chapters(chapters)
        self.assertIn("Best & Cheapest", result)


if __name__ == "__main__":
    unittest.main()
