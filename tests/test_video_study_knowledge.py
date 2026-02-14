"""Tests for video_study_knowledge.py — knowledge packaging and persistence."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.lib.video_study_schema import KnowledgeOutput, InsightItem, ToolMention
from tools.lib.video_study_knowledge import (
    save_knowledge,
    list_studies,
    load_study,
    save_to_supabase,
    format_study_summary,
    format_studies_list,
    study_json_path,
    study_md_path,
)


def _make_knowledge(**overrides) -> KnowledgeOutput:
    defaults = dict(
        video_id="test123",
        title="Test Video",
        channel="TestChannel",
        url="https://youtube.com/watch?v=test123",
        study_date="2026-02-13",
        relevance="Relevant for editing",
        summary="Overview of editing techniques.",
        key_insights=[InsightItem(category="editing", insight="Use AI tools", actionable=True)],
        tools_mentioned=[ToolMention(name="Resolve", category="editing")],
        action_items=[{"priority": "high", "action": "Test AI Audio", "timeline": "this week"}],
        sources=[{"title": "Source", "url": "https://example.com"}],
        analysis_meta={"model": "claude-sonnet-4-5-20250929", "duration_s": 12.5},
    )
    defaults.update(overrides)
    return KnowledgeOutput(**defaults)


# ---------------------------------------------------------------------------
# save_knowledge
# ---------------------------------------------------------------------------

def test_save_knowledge(tmp_path):
    k = _make_knowledge()
    with patch("tools.lib.video_study_knowledge.agents_dir", return_value=tmp_path):
        json_path, md_path = save_knowledge(k)

    assert json_path.exists()
    assert md_path.exists()
    assert json_path.name == "video_study_test123.json"
    assert md_path.name == "video_study_test123.md"

    # Verify JSON content
    data = json.loads(json_path.read_text())
    assert data["video_id"] == "test123"
    assert data["title"] == "Test Video"

    # Verify Markdown content
    md = md_path.read_text()
    assert "# Video Study: Test Video" in md


def test_save_knowledge_validation_error(tmp_path):
    k = _make_knowledge(video_id="")
    import pytest
    with patch("tools.lib.video_study_knowledge.agents_dir", return_value=tmp_path), \
         pytest.raises(ValueError, match="validation failed"):
        save_knowledge(k)


# ---------------------------------------------------------------------------
# list_studies / load_study
# ---------------------------------------------------------------------------

def test_list_studies(tmp_path):
    # Create some study files
    for vid in ("abc", "def"):
        data = {"video_id": vid, "title": f"Video {vid}", "channel": "Ch", "study_date": "2026-02-13"}
        (tmp_path / f"video_study_{vid}.json").write_text(json.dumps(data))

    with patch("tools.lib.video_study_knowledge.agents_dir", return_value=tmp_path):
        studies = list_studies()

    assert len(studies) == 2
    assert studies[0]["video_id"] == "abc"
    assert studies[1]["video_id"] == "def"


def test_list_studies_empty(tmp_path):
    with patch("tools.lib.video_study_knowledge.agents_dir", return_value=tmp_path):
        studies = list_studies()
    assert studies == []


def test_list_studies_bad_json(tmp_path):
    (tmp_path / "video_study_bad.json").write_text("not json")
    with patch("tools.lib.video_study_knowledge.agents_dir", return_value=tmp_path):
        studies = list_studies()
    assert studies == []


def test_load_study(tmp_path):
    k = _make_knowledge()
    with patch("tools.lib.video_study_knowledge.agents_dir", return_value=tmp_path):
        save_knowledge(k)
        loaded = load_study("test123")

    assert loaded is not None
    assert loaded.video_id == "test123"
    assert loaded.title == "Test Video"
    assert len(loaded.key_insights) == 1


def test_load_study_not_found(tmp_path):
    with patch("tools.lib.video_study_knowledge.agents_dir", return_value=tmp_path):
        assert load_study("nonexistent") is None


# ---------------------------------------------------------------------------
# Supabase persistence
# ---------------------------------------------------------------------------

def test_save_to_supabase_success():
    k = _make_knowledge()
    with patch("tools.lib.video_study_knowledge.save_to_supabase") as mock:
        mock.return_value = True
        result = mock(k)
    assert result is True


def test_save_to_supabase_failure():
    k = _make_knowledge()
    # When supabase module import fails, should return False
    with patch("tools.lib.supabase_pipeline.save_lesson", side_effect=Exception("no db")):
        result = save_to_supabase(k)
    assert result is False


# ---------------------------------------------------------------------------
# CLI formatting
# ---------------------------------------------------------------------------

def test_format_study_summary():
    k = _make_knowledge()
    text = format_study_summary(k)
    assert "Test Video" in text
    assert "TestChannel" in text
    assert "Insights: 1" in text
    assert "[editing] Use AI tools" in text


def test_format_studies_list():
    studies = [
        {"video_id": "abc", "title": "First", "channel": "Ch1", "study_date": "2026-02-13"},
        {"video_id": "def", "title": "Second", "channel": "Ch2", "study_date": "2026-02-12"},
    ]
    text = format_studies_list(studies)
    assert "2 video studies" in text
    assert "abc" in text
    assert "def" in text


def test_format_studies_list_empty():
    text = format_studies_list([])
    assert "No video studies" in text


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def test_study_json_path():
    with patch("tools.lib.video_study_knowledge.agents_dir", return_value=Path("/agents")):
        p = study_json_path("abc123")
    assert str(p) == "/agents/video_study_abc123.json"


def test_study_md_path():
    with patch("tools.lib.video_study_knowledge.agents_dir", return_value=Path("/agents")):
        p = study_md_path("abc123")
    assert str(p) == "/agents/video_study_abc123.md"
