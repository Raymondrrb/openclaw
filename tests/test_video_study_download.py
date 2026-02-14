"""Tests for video_study_download.py — download, job dirs, cleanup."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.lib.video_study_download import (
    create_job_dir,
    cleanup_job_dir,
    extract_youtube_id,
    check_ytdlp,
    check_ffmpeg,
    download_video,
    setup_local_file,
    _find_video,
    _find_info_json,
    _find_subtitle,
    TEMP_BASE,
)


# ---------------------------------------------------------------------------
# YouTube ID extraction
# ---------------------------------------------------------------------------

def test_extract_youtube_id_standard():
    assert extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_youtube_id_short():
    assert extract_youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_youtube_id_shorts():
    assert extract_youtube_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_youtube_id_with_params():
    url = "https://www.youtube.com/watch?v=abc_DEF-123&t=60"
    assert extract_youtube_id(url) == "abc_DEF-123"


def test_extract_youtube_id_invalid():
    assert extract_youtube_id("https://example.com/not-youtube") == ""


def test_extract_youtube_id_empty():
    assert extract_youtube_id("") == ""


# ---------------------------------------------------------------------------
# Job directory management
# ---------------------------------------------------------------------------

def test_create_job_dir(tmp_path):
    with patch("tools.lib.video_study_download.TEMP_BASE", tmp_path):
        job_dir = create_job_dir("test_vid")
        assert job_dir.exists()
        assert job_dir.name == "test_vid"


def test_create_job_dir_auto_id(tmp_path):
    with patch("tools.lib.video_study_download.TEMP_BASE", tmp_path):
        job_dir = create_job_dir()
        assert job_dir.exists()
        assert len(job_dir.name) == 12  # hex UUID


def test_cleanup_job_dir(tmp_path):
    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    (job_dir / "file.txt").write_text("data")
    cleanup_job_dir(job_dir)
    assert not job_dir.exists()


def test_cleanup_nonexistent(tmp_path):
    # Should not raise
    cleanup_job_dir(tmp_path / "nonexistent")


# ---------------------------------------------------------------------------
# File finders
# ---------------------------------------------------------------------------

def test_find_video(tmp_path):
    (tmp_path / "video.mp4").write_bytes(b"fake video")
    assert _find_video(tmp_path) == tmp_path / "video.mp4"


def test_find_video_empty(tmp_path):
    assert _find_video(tmp_path) is None


def test_find_video_zero_size(tmp_path):
    (tmp_path / "video.mp4").write_bytes(b"")
    assert _find_video(tmp_path) is None


def test_find_info_json(tmp_path):
    (tmp_path / "video.info.json").write_text("{}")
    assert _find_info_json(tmp_path) == tmp_path / "video.info.json"


def test_find_subtitle_json3(tmp_path):
    (tmp_path / "video.en.json3").write_text("[]", encoding="utf-8")
    assert _find_subtitle(tmp_path) == tmp_path / "video.en.json3"


def test_find_subtitle_prefers_json3(tmp_path):
    (tmp_path / "video.en.json3").write_text("[]")
    (tmp_path / "video.en.vtt").write_text("WEBVTT")
    result = _find_subtitle(tmp_path)
    assert result is not None
    assert result.suffix == ".json3"


# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

def test_check_ytdlp_found():
    with patch("shutil.which", return_value="/usr/local/bin/yt-dlp"):
        assert check_ytdlp() == "/usr/local/bin/yt-dlp"


def test_check_ytdlp_missing():
    with patch("shutil.which", return_value=None):
        assert check_ytdlp() is None


def test_check_ffmpeg_found():
    with patch("shutil.which", return_value="/usr/local/bin/ffmpeg"):
        assert check_ffmpeg() == "/usr/local/bin/ffmpeg"


# ---------------------------------------------------------------------------
# download_video (mocked subprocess)
# ---------------------------------------------------------------------------

def test_download_success(tmp_path):
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    # Pre-create files that yt-dlp would produce
    (job_dir / "video.mp4").write_bytes(b"\x00" * 100)
    info = {"id": "test123", "title": "Test", "channel": "Ch", "description": "Desc", "duration": 300}
    (job_dir / "video.info.json").write_text(json.dumps(info))
    (job_dir / "video.en.json3").write_text('[{"segs":[{"utf8":"hello"}]}]')

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stderr = ""

    with patch("shutil.which", return_value="/usr/local/bin/yt-dlp"), \
         patch("subprocess.run", return_value=mock_proc):
        result = download_video("https://youtube.com/watch?v=test123", job_dir)

    assert result.success
    assert result.video_id == "test123"
    assert result.title == "Test"
    assert result.channel == "Ch"
    assert result.duration_s == 300.0
    assert result.subtitle_path is not None


def test_download_ytdlp_missing(tmp_path):
    with patch("shutil.which", return_value=None):
        result = download_video("https://youtube.com/watch?v=x", tmp_path)
    assert not result.success
    assert "yt-dlp not found" in result.error


def test_download_failure(tmp_path):
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "ERROR: Video unavailable"

    with patch("shutil.which", return_value="/usr/local/bin/yt-dlp"), \
         patch("subprocess.run", return_value=mock_proc):
        result = download_video("https://youtube.com/watch?v=bad", tmp_path)

    assert not result.success
    assert "yt-dlp failed" in result.error


def test_download_timeout(tmp_path):
    import subprocess as sp
    with patch("shutil.which", return_value="/usr/local/bin/yt-dlp"), \
         patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="yt-dlp", timeout=600)):
        result = download_video("https://youtube.com/watch?v=slow", tmp_path)
    assert not result.success
    assert "timed out" in result.error


# ---------------------------------------------------------------------------
# setup_local_file
# ---------------------------------------------------------------------------

def test_setup_local_file(tmp_path):
    src = tmp_path / "my_video.mp4"
    src.write_bytes(b"video data")
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    result = setup_local_file(str(src), job_dir)
    assert result.success
    assert result.video_id == "my_video"
    assert result.video_path.exists()


def test_setup_local_file_not_found(tmp_path):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    result = setup_local_file("/nonexistent/file.mp4", job_dir)
    assert not result.success
    assert "not found" in result.error
