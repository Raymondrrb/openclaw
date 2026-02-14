"""Tests for video_study_schema.py — dataclasses, validation, serialization."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.lib.video_study_schema import (
    INSIGHT_CATEGORIES,
    ACTION_PRIORITIES,
    FRAME_STRATEGIES,
    InsightItem,
    ToolMention,
    StudyConfig,
    KnowledgeOutput,
    knowledge_to_markdown,
)


# ---------------------------------------------------------------------------
# InsightItem
# ---------------------------------------------------------------------------

def test_insight_item_valid():
    item = InsightItem(category="editing", insight="Use AI Audio Assistant")
    assert item.validate() == []


def test_insight_item_invalid_category():
    item = InsightItem(category="invalid_cat", insight="Something")
    errors = item.validate()
    assert any("Invalid insight category" in e for e in errors)


def test_insight_item_empty_insight():
    item = InsightItem(category="editing", insight="  ")
    errors = item.validate()
    assert any("empty" in e for e in errors)


# ---------------------------------------------------------------------------
# ToolMention
# ---------------------------------------------------------------------------

def test_tool_mention_valid():
    tool = ToolMention(name="DaVinci Resolve", category="editing")
    assert tool.validate() == []


def test_tool_mention_empty_name():
    tool = ToolMention(name="  ")
    errors = tool.validate()
    assert any("empty" in e for e in errors)


# ---------------------------------------------------------------------------
# StudyConfig
# ---------------------------------------------------------------------------

def test_study_config_url():
    cfg = StudyConfig(url="https://youtube.com/watch?v=test123")
    assert cfg.validate() == []


def test_study_config_file(tmp_path):
    f = tmp_path / "video.mp4"
    f.write_bytes(b"fake")
    cfg = StudyConfig(file_path=str(f))
    assert cfg.validate() == []


def test_study_config_neither():
    cfg = StudyConfig()
    errors = cfg.validate()
    assert any("Either url or file_path" in e for e in errors)


def test_study_config_both(tmp_path):
    f = tmp_path / "video.mp4"
    f.write_bytes(b"fake")
    cfg = StudyConfig(url="https://example.com", file_path=str(f))
    errors = cfg.validate()
    assert any("not both" in e for e in errors)


def test_study_config_bad_max_frames():
    cfg = StudyConfig(url="https://x.com", max_frames=0)
    errors = cfg.validate()
    assert any("max_frames" in e for e in errors)


def test_study_config_bad_strategy():
    cfg = StudyConfig(url="https://x.com", frame_strategy="random")
    errors = cfg.validate()
    assert any("frame_strategy" in e for e in errors)


def test_study_config_file_not_found():
    cfg = StudyConfig(file_path="/nonexistent/video.mp4")
    errors = cfg.validate()
    assert any("File not found" in e for e in errors)


# ---------------------------------------------------------------------------
# KnowledgeOutput
# ---------------------------------------------------------------------------

def _make_knowledge(**overrides) -> KnowledgeOutput:
    """Create a valid KnowledgeOutput with sensible defaults."""
    defaults = dict(
        video_id="test123",
        title="Test Video",
        channel="TestChannel",
        url="https://youtube.com/watch?v=test123",
        study_date="2026-02-13",
        relevance="Relevant for editing workflow",
        summary="This video covers editing techniques.",
        key_insights=[InsightItem(category="editing", insight="Use shortcuts")],
        tools_mentioned=[ToolMention(name="DaVinci Resolve")],
        action_items=[{"priority": "high", "action": "Test tools", "timeline": "this week"}],
        integration_plan=[{"phase": "Phase 1", "steps": ["Install plugin"]}],
        transcript_highlights=[{"timestamp": "2:30", "text": "Key point", "note": "Important"}],
        sources=[{"title": "Video", "url": "https://example.com"}],
        analysis_meta={"model": "claude-sonnet-4-5-20250929", "frame_count": 20},
    )
    defaults.update(overrides)
    return KnowledgeOutput(**defaults)


def test_knowledge_valid():
    k = _make_knowledge()
    assert k.validate() == []


def test_knowledge_missing_video_id():
    k = _make_knowledge(video_id="")
    errors = k.validate()
    assert any("video_id" in e for e in errors)


def test_knowledge_missing_title():
    k = _make_knowledge(title="")
    errors = k.validate()
    assert any("title" in e for e in errors)


def test_knowledge_missing_summary():
    k = _make_knowledge(summary="")
    errors = k.validate()
    assert any("summary" in e for e in errors)


def test_knowledge_no_insights():
    k = _make_knowledge(key_insights=[])
    errors = k.validate()
    assert any("key_insight" in e for e in errors)


def test_knowledge_bad_insight_propagates():
    k = _make_knowledge(
        key_insights=[InsightItem(category="invalid", insight="x")]
    )
    errors = k.validate()
    assert any("key_insights[0]" in e for e in errors)


def test_knowledge_bad_action_priority():
    k = _make_knowledge(
        action_items=[{"priority": "critical", "action": "Do thing"}]
    )
    errors = k.validate()
    assert any("priority" in e for e in errors)


def test_knowledge_action_missing_action_key():
    k = _make_knowledge(action_items=[{"priority": "high"}])
    errors = k.validate()
    assert any("missing 'action'" in e for e in errors)


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

def test_to_json_and_back():
    k = _make_knowledge()
    json_str = k.to_json()
    parsed = json.loads(json_str)
    assert parsed["video_id"] == "test123"
    assert parsed["key_insights"][0]["category"] == "editing"

    k2 = KnowledgeOutput.from_json(json_str)
    assert k2.video_id == k.video_id
    assert k2.title == k.title
    assert len(k2.key_insights) == 1
    assert isinstance(k2.key_insights[0], InsightItem)
    assert k2.key_insights[0].category == "editing"


def test_from_dict():
    data = {
        "video_id": "abc",
        "title": "Title",
        "channel": "Ch",
        "url": "",
        "study_date": "2026-01-01",
        "relevance": "Relevant",
        "summary": "Summary text",
        "key_insights": [{"category": "tools", "insight": "Use X"}],
        "tools_mentioned": [{"name": "X"}],
    }
    k = KnowledgeOutput.from_dict(data)
    assert k.video_id == "abc"
    assert isinstance(k.key_insights[0], InsightItem)
    assert isinstance(k.tools_mentioned[0], ToolMention)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def test_knowledge_to_markdown():
    k = _make_knowledge()
    md = knowledge_to_markdown(k)
    assert "# Video Study: Test Video" in md
    assert "**Channel:** TestChannel" in md
    assert "## Key Insights" in md
    assert "### Editing" in md
    assert "Use shortcuts" in md
    assert "## Tools Mentioned" in md
    assert "DaVinci Resolve" in md
    assert "## Action Items" in md
    assert "[HIGH]" in md
    assert "## Integration Plan" in md
    assert "## Transcript Highlights" in md
    assert "## Sources" in md


def test_markdown_empty_optional_sections():
    k = _make_knowledge(
        tools_mentioned=[],
        action_items=[],
        integration_plan=[],
        transcript_highlights=[],
        sources=[],
        analysis_meta={},
    )
    md = knowledge_to_markdown(k)
    assert "## Key Insights" in md
    assert "## Tools Mentioned" not in md
    assert "## Action Items" not in md


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_insight_categories():
    assert "editing" in INSIGHT_CATEGORIES
    assert "audio" in INSIGHT_CATEGORIES
    assert "dzine" in INSIGHT_CATEGORIES
    assert len(INSIGHT_CATEGORIES) == 11


def test_action_priorities():
    assert ACTION_PRIORITIES == {"high", "medium", "low"}


def test_frame_strategies():
    assert FRAME_STRATEGIES == {"scene", "interval"}
