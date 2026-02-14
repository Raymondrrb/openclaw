"""Video Study pipeline — data schemas and validation.

Dataclasses for all pipeline artifacts: study config, knowledge output,
insight items, tool mentions, and analysis metadata.

Stdlib only — no external deps.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Valid insight categories
INSIGHT_CATEGORIES = frozenset({
    "editing", "audio", "thumbnail", "scripting", "growth",
    "affiliate", "dzine", "workflow", "tools", "seo", "general",
})

# Valid action item priorities
ACTION_PRIORITIES = frozenset({"high", "medium", "low"})

# Frame extraction strategies
FRAME_STRATEGIES = frozenset({"scene", "interval"})


# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------

@dataclass
class InsightItem:
    """A single categorized insight from a video study."""
    category: str
    insight: str
    details: str = ""
    actionable: bool = False

    def validate(self) -> list[str]:
        errors = []
        if self.category not in INSIGHT_CATEGORIES:
            errors.append(f"Invalid insight category: {self.category!r}")
        if not self.insight.strip():
            errors.append("Insight text is empty")
        return errors


@dataclass
class ToolMention:
    """A tool, plugin, or service discovered in a video study."""
    name: str
    category: str = ""
    url: str = ""
    note: str = ""

    def validate(self) -> list[str]:
        errors = []
        if not self.name.strip():
            errors.append("Tool name is empty")
        return errors


# ---------------------------------------------------------------------------
# Study config (input)
# ---------------------------------------------------------------------------

@dataclass
class StudyConfig:
    """Configuration for a video study run."""
    url: str = ""
    file_path: str = ""
    context: str = ""
    max_frames: int = 80
    frame_strategy: str = "scene"
    video_id: str = ""

    def validate(self) -> list[str]:
        errors = []
        if not self.url and not self.file_path:
            errors.append("Either url or file_path is required")
        if self.url and self.file_path:
            errors.append("Provide url or file_path, not both")
        if self.file_path and not Path(self.file_path).is_file():
            errors.append(f"File not found: {self.file_path}")
        if self.max_frames < 1 or self.max_frames > 500:
            errors.append(f"max_frames must be 1-500, got {self.max_frames}")
        if self.frame_strategy not in FRAME_STRATEGIES:
            errors.append(f"Invalid frame_strategy: {self.frame_strategy!r}")
        return errors


# ---------------------------------------------------------------------------
# Knowledge output (result)
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeOutput:
    """Structured knowledge extracted from a video study."""
    video_id: str
    title: str
    channel: str
    url: str
    study_date: str
    relevance: str
    summary: str
    key_insights: list[InsightItem] = field(default_factory=list)
    tools_mentioned: list[ToolMention] = field(default_factory=list)
    action_items: list[dict] = field(default_factory=list)
    integration_plan: list[dict] = field(default_factory=list)
    transcript_highlights: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    analysis_meta: dict = field(default_factory=dict)

    def validate(self) -> list[str]:
        errors = []
        if not self.video_id:
            errors.append("video_id is required")
        if not self.title:
            errors.append("title is required")
        if not self.summary:
            errors.append("summary is required")
        if not self.study_date:
            errors.append("study_date is required")
        if not self.key_insights:
            errors.append("At least one key_insight is required")
        for i, item in enumerate(self.key_insights):
            for err in item.validate():
                errors.append(f"key_insights[{i}]: {err}")
        for i, tool in enumerate(self.tools_mentioned):
            for err in tool.validate():
                errors.append(f"tools_mentioned[{i}]: {err}")
        for i, ai in enumerate(self.action_items):
            if "action" not in ai:
                errors.append(f"action_items[{i}]: missing 'action' key")
            pri = ai.get("priority", "")
            if pri and pri not in ACTION_PRIORITIES:
                errors.append(f"action_items[{i}]: invalid priority {pri!r}")
        return errors

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        d = asdict(self)
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeOutput:
        """Deserialize from a dict (e.g. from JSON)."""
        insights = [
            InsightItem(**item) if isinstance(item, dict) else item
            for item in data.get("key_insights", [])
        ]
        tools = [
            ToolMention(**item) if isinstance(item, dict) else item
            for item in data.get("tools_mentioned", [])
        ]
        return cls(
            video_id=data.get("video_id", ""),
            title=data.get("title", ""),
            channel=data.get("channel", ""),
            url=data.get("url", ""),
            study_date=data.get("study_date", ""),
            relevance=data.get("relevance", ""),
            summary=data.get("summary", ""),
            key_insights=insights,
            tools_mentioned=tools,
            action_items=data.get("action_items", []),
            integration_plan=data.get("integration_plan", []),
            transcript_highlights=data.get("transcript_highlights", []),
            sources=data.get("sources", []),
            analysis_meta=data.get("analysis_meta", {}),
        )

    @classmethod
    def from_json(cls, text: str) -> KnowledgeOutput:
        return cls.from_dict(json.loads(text))


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def knowledge_to_markdown(k: KnowledgeOutput) -> str:
    """Render KnowledgeOutput as a markdown document matching agents/video_study_*.md format."""
    lines: list[str] = []

    lines.append(f"# Video Study: {k.title}")
    lines.append("")
    lines.append(f"**Channel:** {k.channel}")
    lines.append(f"**URL:** {k.url}")
    lines.append(f"**Study Date:** {k.study_date}")
    lines.append(f"**Video ID:** {k.video_id}")
    lines.append("")

    lines.append("## Relevance to Rayviews")
    lines.append("")
    lines.append(k.relevance)
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(k.summary)
    lines.append("")

    if k.key_insights:
        lines.append("## Key Insights")
        lines.append("")
        by_cat: dict[str, list[InsightItem]] = {}
        for item in k.key_insights:
            by_cat.setdefault(item.category, []).append(item)
        for cat in sorted(by_cat.keys()):
            lines.append(f"### {cat.title()}")
            lines.append("")
            for item in by_cat[cat]:
                marker = " [actionable]" if item.actionable else ""
                lines.append(f"- **{item.insight}**{marker}")
                if item.details:
                    lines.append(f"  {item.details}")
            lines.append("")

    if k.tools_mentioned:
        lines.append("## Tools Mentioned")
        lines.append("")
        lines.append("| Tool | Category | Note |")
        lines.append("|------|----------|------|")
        for t in k.tools_mentioned:
            name = f"[{t.name}]({t.url})" if t.url else t.name
            lines.append(f"| {name} | {t.category} | {t.note} |")
        lines.append("")

    if k.action_items:
        lines.append("## Action Items")
        lines.append("")
        for ai in k.action_items:
            pri = ai.get("priority", "medium").upper()
            action = ai.get("action", "")
            timeline = ai.get("timeline", "")
            tl = f" ({timeline})" if timeline else ""
            lines.append(f"- [{pri}] {action}{tl}")
        lines.append("")

    if k.integration_plan:
        lines.append("## Integration Plan")
        lines.append("")
        for phase in k.integration_plan:
            lines.append(f"### {phase.get('phase', 'Phase')}")
            lines.append("")
            for step in phase.get("steps", []):
                lines.append(f"- {step}")
            lines.append("")

    if k.transcript_highlights:
        lines.append("## Transcript Highlights")
        lines.append("")
        for h in k.transcript_highlights:
            ts = h.get("timestamp", "")
            text = h.get("text", "")
            note = h.get("note", "")
            prefix = f"**[{ts}]** " if ts else ""
            suffix = f" — *{note}*" if note else ""
            lines.append(f"- {prefix}{text}{suffix}")
        lines.append("")

    if k.sources:
        lines.append("## Sources")
        lines.append("")
        for s in k.sources:
            title = s.get("title", "")
            url = s.get("url", "")
            if url:
                lines.append(f"- [{title or url}]({url})")
            elif title:
                lines.append(f"- {title}")
        lines.append("")

    if k.analysis_meta:
        lines.append("---")
        lines.append("")
        lines.append("*Analysis metadata:*")
        meta = k.analysis_meta
        parts = []
        if "model" in meta:
            parts.append(f"Model: {meta['model']}")
        if "frame_count" in meta:
            parts.append(f"Frames analyzed: {meta['frame_count']}")
        if "input_tokens" in meta:
            parts.append(f"Input tokens: {meta['input_tokens']}")
        if "output_tokens" in meta:
            parts.append(f"Output tokens: {meta['output_tokens']}")
        if "duration_s" in meta:
            parts.append(f"Duration: {meta['duration_s']:.1f}s")
        if parts:
            lines.append(f"*{' | '.join(parts)}*")
        lines.append("")

    return "\n".join(lines)
