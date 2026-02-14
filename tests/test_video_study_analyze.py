"""Tests for video_study_analyze.py — Anthropic multimodal analysis."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.lib.video_study_analyze import (
    analyze_video,
    _extract_json,
    _build_user_content,
    _encode_frame,
    SYSTEM_PROMPT,
    MAX_API_FRAMES,
    MAX_TRANSCRIPT_CHARS,
)


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def test_extract_json_plain():
    text = '{"key": "value"}'
    assert _extract_json(text) == {"key": "value"}


def test_extract_json_with_fences():
    text = '```json\n{"key": "value"}\n```'
    assert _extract_json(text) == {"key": "value"}


def test_extract_json_with_whitespace():
    text = '\n  {"key": "value"}  \n'
    assert _extract_json(text) == {"key": "value"}


# ---------------------------------------------------------------------------
# Frame encoding
# ---------------------------------------------------------------------------

def test_encode_frame_jpeg(tmp_path):
    f = tmp_path / "frame.jpg"
    f.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)
    result = _encode_frame(f)
    assert result["type"] == "image"
    assert result["source"]["media_type"] == "image/jpeg"
    assert result["source"]["type"] == "base64"
    assert len(result["source"]["data"]) > 0


def test_encode_frame_png(tmp_path):
    f = tmp_path / "frame.png"
    f.write_bytes(b"\x89PNG" + b"\x00" * 10)
    result = _encode_frame(f)
    assert result["source"]["media_type"] == "image/png"


# ---------------------------------------------------------------------------
# Content building
# ---------------------------------------------------------------------------

def test_build_user_content_text_only():
    content = _build_user_content(
        title="Test Video",
        channel="TestChannel",
        description="A test description",
        transcript_text="[0:00] Hello world",
        frames=[],
        context="DaVinci Resolve",
    )
    assert len(content) == 1
    assert content[0]["type"] == "text"
    assert "Test Video" in content[0]["text"]
    assert "TestChannel" in content[0]["text"]
    assert "DaVinci Resolve" in content[0]["text"]
    assert "Hello world" in content[0]["text"]


def test_build_user_content_with_frames(tmp_path):
    frames = []
    for i in range(3):
        f = tmp_path / f"frame_{i}.jpg"
        f.write_bytes(b"\xff" * 20)
        frames.append(f)

    content = _build_user_content(
        title="Test",
        channel="",
        description="",
        transcript_text="",
        frames=frames,
    )
    # text + 3 images + trailing text
    assert len(content) == 5
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image"
    assert content[2]["type"] == "image"
    assert content[3]["type"] == "image"
    assert content[4]["type"] == "text"


def test_build_user_content_caps_frames(tmp_path):
    frames = []
    for i in range(30):
        f = tmp_path / f"frame_{i}.jpg"
        f.write_bytes(b"\xff" * 20)
        frames.append(f)

    content = _build_user_content("T", "", "", "", frames)
    image_blocks = [c for c in content if c["type"] == "image"]
    assert len(image_blocks) == MAX_API_FRAMES


def test_build_user_content_truncates_transcript():
    long_text = "a" * 50000
    content = _build_user_content("T", "", "", long_text, [])
    text = content[0]["text"]
    # Should be truncated to MAX_TRANSCRIPT_CHARS
    assert len(text) < 50000


# ---------------------------------------------------------------------------
# analyze_video (mocked API)
# ---------------------------------------------------------------------------

def _mock_api_response():
    """Build a valid Anthropic API response with knowledge JSON."""
    knowledge = {
        "relevance": "Relevant for editing workflow",
        "summary": "This video covers editing techniques for DaVinci Resolve.",
        "key_insights": [
            {
                "category": "editing",
                "insight": "Use AI Audio Assistant",
                "details": "One-click professional audio mix",
                "actionable": True,
            }
        ],
        "tools_mentioned": [
            {"name": "DaVinci Resolve", "category": "editing", "url": "", "note": "NLE"}
        ],
        "action_items": [
            {"priority": "high", "action": "Test AI Audio", "timeline": "this week"}
        ],
        "integration_plan": [
            {"phase": "Phase 1", "steps": ["Install plugin"]}
        ],
        "transcript_highlights": [
            {"timestamp": "2:30", "text": "Key technique", "note": "Important"}
        ],
        "sources": [
            {"title": "DaVinci Resolve", "url": "https://blackmagicdesign.com"}
        ],
    }
    return {
        "content": [{"type": "text", "text": json.dumps(knowledge)}],
        "model": "claude-sonnet-4-5-20250929",
        "usage": {"input_tokens": 5000, "output_tokens": 800},
    }


def test_analyze_video_success():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}), \
         patch("tools.lib.video_study_analyze._post_json", return_value=_mock_api_response()):
        knowledge, meta = analyze_video(
            title="Test Video",
            channel="TestChannel",
            description="Desc",
            transcript_text="[0:00] Hello",
            frames=[],
        )

    assert knowledge is not None
    assert knowledge.title == "Test Video"
    assert len(knowledge.key_insights) == 1
    assert knowledge.key_insights[0].category == "editing"
    assert meta["model"] == "claude-sonnet-4-5-20250929"
    assert meta["input_tokens"] == 5000


def test_analyze_video_no_api_key():
    with patch.dict("os.environ", {}, clear=True):
        # Remove ANTHROPIC_API_KEY from env
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        knowledge, meta = analyze_video("T", "C", "", "", [])

    assert knowledge is None
    assert "ANTHROPIC_API_KEY" in meta["error"]


def test_analyze_video_api_error():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}), \
         patch("tools.lib.video_study_analyze._post_json", side_effect=RuntimeError("HTTP 500")):
        knowledge, meta = analyze_video("T", "C", "", "", [])

    assert knowledge is None
    assert "HTTP 500" in meta["error"]


def test_analyze_video_bad_json():
    bad_response = {
        "content": [{"type": "text", "text": "Not valid JSON at all"}],
        "model": "test",
        "usage": {},
    }
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}), \
         patch("tools.lib.video_study_analyze._post_json", return_value=bad_response):
        knowledge, meta = analyze_video("T", "C", "", "", [])

    assert knowledge is None
    assert "Failed to parse JSON" in meta["error"]


def test_analyze_video_empty_response():
    empty_response = {"content": [], "model": "test", "usage": {}}
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}), \
         patch("tools.lib.video_study_analyze._post_json", return_value=empty_response):
        knowledge, meta = analyze_video("T", "C", "", "", [])

    assert knowledge is None
    assert "No text" in meta["error"]


# ---------------------------------------------------------------------------
# System prompt sanity
# ---------------------------------------------------------------------------

def test_system_prompt_mentions_categories():
    for cat in ["editing", "audio", "thumbnail", "dzine", "growth"]:
        assert cat in SYSTEM_PROMPT
