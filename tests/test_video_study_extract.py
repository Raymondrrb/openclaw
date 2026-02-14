"""Tests for video_study_extract.py — frames, transcript parsing."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.lib.video_study_extract import (
    parse_json3_captions,
    parse_vtt_captions,
    segments_to_text,
    extract_frames_scene,
    extract_frames_interval,
    sample_frames,
    extract_all,
    _format_timestamp,
    _subsample,
    TranscriptSegment,
)


# ---------------------------------------------------------------------------
# json3 parsing
# ---------------------------------------------------------------------------

def test_parse_json3_events_format(tmp_path):
    data = {
        "events": [
            {"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "Hello world"}]},
            {"tStartMs": 4000, "dDurationMs": 1500, "segs": [{"utf8": "Second line"}]},
        ]
    }
    f = tmp_path / "subs.json3"
    f.write_text(json.dumps(data))
    segs = parse_json3_captions(f)
    assert len(segs) == 2
    assert segs[0].text == "Hello world"
    assert segs[0].start_s == 1.0
    assert segs[0].end_s == 3.0
    assert segs[1].text == "Second line"


def test_parse_json3_list_format(tmp_path):
    data = [
        {"tStartMs": 500, "dDurationMs": 1000, "segs": [{"utf8": "Line one"}]},
    ]
    f = tmp_path / "subs.json3"
    f.write_text(json.dumps(data))
    segs = parse_json3_captions(f)
    assert len(segs) == 1
    assert segs[0].start_s == 0.5


def test_parse_json3_skips_empty(tmp_path):
    data = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 100, "segs": [{"utf8": "\n"}]},
            {"tStartMs": 100, "dDurationMs": 100, "segs": [{"utf8": "  "}]},
            {"tStartMs": 200, "dDurationMs": 100, "segs": [{"utf8": "Real text"}]},
        ]
    }
    f = tmp_path / "subs.json3"
    f.write_text(json.dumps(data))
    segs = parse_json3_captions(f)
    assert len(segs) == 1
    assert segs[0].text == "Real text"


def test_parse_json3_multi_segment(tmp_path):
    data = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 1000, "segs": [
                {"utf8": "Part "},
                {"utf8": "one"},
            ]},
        ]
    }
    f = tmp_path / "subs.json3"
    f.write_text(json.dumps(data))
    segs = parse_json3_captions(f)
    assert segs[0].text == "Part one"


def test_parse_json3_bad_file(tmp_path):
    f = tmp_path / "bad.json3"
    f.write_text("not json")
    assert parse_json3_captions(f) == []


def test_parse_json3_missing_file(tmp_path):
    assert parse_json3_captions(tmp_path / "missing.json3") == []


# ---------------------------------------------------------------------------
# VTT parsing
# ---------------------------------------------------------------------------

def test_parse_vtt(tmp_path):
    vtt = """WEBVTT

00:00:01.000 --> 00:00:04.000
Hello world

00:00:05.000 --> 00:00:08.000
Second line
"""
    f = tmp_path / "subs.vtt"
    f.write_text(vtt)
    segs = parse_vtt_captions(f)
    assert len(segs) == 2
    assert segs[0].text == "Hello world"
    assert segs[0].start_s == 1.0
    assert segs[0].end_s == 4.0


def test_parse_vtt_with_tags(tmp_path):
    vtt = """WEBVTT

00:00:01.000 --> 00:00:04.000
<c>Hello</c> <c>world</c>
"""
    f = tmp_path / "subs.vtt"
    f.write_text(vtt)
    segs = parse_vtt_captions(f)
    assert segs[0].text == "Hello world"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_format_timestamp():
    assert _format_timestamp(0) == "0:00"
    assert _format_timestamp(65) == "1:05"
    assert _format_timestamp(3661) == "1:01:01"


def test_segments_to_text():
    segs = [
        TranscriptSegment(start_s=0, end_s=2, text="Hello"),
        TranscriptSegment(start_s=65, end_s=70, text="World"),
    ]
    text = segments_to_text(segs)
    assert "[0:00] Hello" in text
    assert "[1:05] World" in text


def test_subsample():
    items = list(range(100))
    paths = [Path(f"frame_{i:04d}.jpg") for i in items]
    result = _subsample(paths, 10)
    assert len(result) == 10
    assert result[0] == paths[0]


def test_subsample_fewer_than_target():
    paths = [Path(f"frame_{i}.jpg") for i in range(5)]
    result = _subsample(paths, 10)
    assert len(result) == 5


def test_sample_frames():
    paths = [Path(f"f{i}.jpg") for i in range(50)]
    result = sample_frames(paths, 10)
    assert len(result) == 10


# ---------------------------------------------------------------------------
# Frame extraction (mocked ffmpeg)
# ---------------------------------------------------------------------------

def test_extract_frames_scene_success(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    out_dir = tmp_path / "frames"

    def fake_run(cmd, **kwargs):
        out_dir.mkdir(exist_ok=True)
        for i in range(10):
            (out_dir / f"frame_{i:04d}.jpg").write_bytes(b"\xff" * 100)
        return MagicMock(returncode=0)

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("subprocess.run", side_effect=fake_run):
        frames = extract_frames_scene(video, out_dir, max_frames=80)

    assert len(frames) == 10


def test_extract_frames_scene_no_ffmpeg(tmp_path):
    with patch("tools.lib.video_study_download.check_ffmpeg", return_value=None), \
         patch("tools.lib.video_study_extract.check_ffmpeg", return_value=None):
        frames = extract_frames_scene(tmp_path / "v.mp4", tmp_path / "f")
    assert frames == []


def test_extract_frames_interval_success(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    out_dir = tmp_path / "frames"

    def fake_run(cmd, **kwargs):
        out_dir.mkdir(exist_ok=True)
        for i in range(20):
            (out_dir / f"frame_{i:04d}.jpg").write_bytes(b"\xff" * 100)
        return MagicMock(returncode=0)

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("subprocess.run", side_effect=fake_run):
        frames = extract_frames_interval(video, out_dir, max_frames=10)

    assert len(frames) == 10  # subsampled from 20


# ---------------------------------------------------------------------------
# Full extraction
# ---------------------------------------------------------------------------

def test_extract_all_with_subs(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    sub_file = tmp_path / "subs.json3"
    sub_file.write_text(json.dumps({
        "events": [{"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "Hello"}]}]
    }))
    frames_dir = tmp_path / "frames"

    def fake_run(cmd, **kwargs):
        frames_dir.mkdir(exist_ok=True)
        for i in range(5):
            (frames_dir / f"frame_{i:04d}.jpg").write_bytes(b"\xff" * 50)
        return MagicMock(returncode=0)

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("subprocess.run", side_effect=fake_run):
        result = extract_all(video, tmp_path, subtitle_path=sub_file)

    assert result.success
    assert len(result.transcript) == 1
    assert "Hello" in result.transcript_text
    assert len(result.frames) == 5


def test_extract_all_no_data(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("subprocess.run", return_value=MagicMock(returncode=0)):
        result = extract_all(video, tmp_path)

    assert not result.success
    assert "No frames" in result.error
