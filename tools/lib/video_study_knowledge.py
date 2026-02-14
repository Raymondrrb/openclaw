"""Video Study pipeline — knowledge packaging and persistence.

Packages analysis results into knowledge.json + knowledge.md,
saves to agents/ directory and Supabase (fire-and-forget).

Stdlib only — no external deps.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import project_root, now_iso
from tools.lib.video_study_schema import KnowledgeOutput, knowledge_to_markdown


# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------

def agents_dir() -> Path:
    """Return the agents/ directory."""
    return project_root() / "agents"


def study_json_path(video_id: str) -> Path:
    """Path for knowledge JSON: agents/video_study_<id>.json"""
    return agents_dir() / f"video_study_{video_id}.json"


def study_md_path(video_id: str) -> Path:
    """Path for knowledge markdown: agents/video_study_<id>.md"""
    return agents_dir() / f"video_study_{video_id}.md"


# ---------------------------------------------------------------------------
# Save knowledge files
# ---------------------------------------------------------------------------

def save_knowledge(knowledge: KnowledgeOutput) -> tuple[Path, Path]:
    """Save knowledge.json and knowledge.md to agents/ directory.

    Returns (json_path, md_path).
    """
    vid = knowledge.video_id

    # Validate before saving
    errors = knowledge.validate()
    if errors:
        raise ValueError(f"Knowledge validation failed: {'; '.join(errors)}")

    # Save JSON
    json_path = study_json_path(vid)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(knowledge.to_json(), encoding="utf-8")

    # Save Markdown
    md_path = study_md_path(vid)
    md_text = knowledge_to_markdown(knowledge)
    md_path.write_text(md_text, encoding="utf-8")

    return json_path, md_path


# ---------------------------------------------------------------------------
# List existing studies
# ---------------------------------------------------------------------------

def list_studies() -> list[dict]:
    """List all existing video study files in agents/ directory."""
    studies = []
    for json_file in sorted(agents_dir().glob("video_study_*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            studies.append({
                "video_id": data.get("video_id", ""),
                "title": data.get("title", ""),
                "channel": data.get("channel", ""),
                "study_date": data.get("study_date", ""),
                "json_path": str(json_file),
                "md_path": str(json_file.with_suffix(".md")),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return studies


def load_study(video_id: str) -> KnowledgeOutput | None:
    """Load a study from agents/ by video_id."""
    path = study_json_path(video_id)
    if not path.is_file():
        return None
    try:
        return KnowledgeOutput.from_json(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Supabase persistence (fire-and-forget)
# ---------------------------------------------------------------------------

def save_to_supabase(knowledge: KnowledgeOutput) -> bool:
    """Save study results to Supabase lessons table. Never raises."""
    try:
        from tools.lib.supabase_pipeline import save_lesson, set_channel_memory

        # Save as a lesson
        save_lesson(
            scope="video_study",
            trigger=f"study:{knowledge.video_id}",
            rule=knowledge.summary[:200],
            example={
                "video_id": knowledge.video_id,
                "title": knowledge.title,
                "channel": knowledge.channel,
                "url": knowledge.url,
                "study_date": knowledge.study_date,
                "insight_count": len(knowledge.key_insights),
                "action_count": len(knowledge.action_items),
            },
            severity="info",
        )

        # Update channel memory with latest study
        set_channel_memory(f"last_study_{knowledge.video_id}", {
            "title": knowledge.title,
            "channel": knowledge.channel,
            "study_date": knowledge.study_date,
            "insights": len(knowledge.key_insights),
            "updated_at": now_iso(),
        })

        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Format for CLI display
# ---------------------------------------------------------------------------

def format_study_summary(knowledge: KnowledgeOutput) -> str:
    """Format a study for CLI display."""
    lines = []
    lines.append(f"  Title:    {knowledge.title}")
    lines.append(f"  Channel:  {knowledge.channel}")
    lines.append(f"  URL:      {knowledge.url}")
    lines.append(f"  Date:     {knowledge.study_date}")
    lines.append(f"  Insights: {len(knowledge.key_insights)}")
    lines.append(f"  Tools:    {len(knowledge.tools_mentioned)}")
    lines.append(f"  Actions:  {len(knowledge.action_items)}")

    if knowledge.key_insights:
        lines.append("")
        lines.append("  Top insights:")
        for item in knowledge.key_insights[:5]:
            marker = " *" if item.actionable else ""
            lines.append(f"    [{item.category}] {item.insight}{marker}")

    return "\n".join(lines)


def format_studies_list(studies: list[dict]) -> str:
    """Format study list for CLI display."""
    if not studies:
        return "No video studies found."

    lines = [f"Found {len(studies)} video studies:\n"]
    for s in studies:
        vid = s["video_id"]
        title = s["title"][:50] or "(untitled)"
        channel = s["channel"] or "?"
        date = s["study_date"][:10] or "?"
        lines.append(f"  {vid}  {date}  {channel:<20s}  {title}")

    return "\n".join(lines)
