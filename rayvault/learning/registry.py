"""Global Learning Event Registry — cross-video queries and pattern detection.

Provides the read-only query layer over learning events. Events are written
by tools/learning_event.py; this module only reads.

Stdlib only.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from tools.lib.common import project_root


EVENTS_PATH: Path = project_root() / "data" / "learning_events.json"
REPORTS_DIR: Path = project_root() / "data" / "learning_reports"


def _load_all_events(path: Path | None = None) -> list[dict]:
    p = path or EVENTS_PATH
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def query_events(
    *,
    component: str = "",
    severity: str = "",
    date_from: str = "",
    date_to: str = "",
    video_id: str = "",
    status: str = "",
    _path: Path | None = None,
) -> list[dict]:
    """Cross-video event search with flexible filters."""
    events = _load_all_events(_path)
    result = []
    for e in events:
        if component and e.get("component") != component:
            continue
        if severity and e.get("severity") != severity:
            continue
        if video_id and e.get("video_id") != video_id:
            continue
        if status and e.get("status") != status:
            continue
        ts = e.get("timestamp", "")
        if date_from and ts < date_from:
            continue
        if date_to and ts > date_to:
            continue
        result.append(e)
    return result


def get_patterns(*, min_count: int = 2, _path: Path | None = None) -> list[dict]:
    """Group events by component+root_cause and return recurring patterns."""
    events = _load_all_events(_path)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for e in events:
        key = (e.get("component", ""), e.get("root_cause", "")[:80])
        groups[key].append(e)

    patterns = []
    for (component, root_cause), items in sorted(groups.items()):
        if len(items) < min_count:
            continue
        patterns.append({
            "component": component,
            "root_cause": root_cause,
            "count": len(items),
            "severities": list({i.get("severity", "") for i in items}),
            "video_ids": sorted({i.get("video_id", "") for i in items if i.get("video_id")}),
            "latest": max(i.get("timestamp", "") for i in items),
            "statuses": list({i.get("status", "") for i in items}),
        })

    return sorted(patterns, key=lambda p: p["count"], reverse=True)


def get_agent_learnings(agent: str, *, _path: Path | None = None) -> list[dict]:
    """Get learning events for an agent's components.

    Maps agent name to known components and returns relevant events.
    """
    agent_components = {
        "market_scout": ["research", "niche", "day"],
        "researcher": ["research", "amazon", "products"],
        "scriptwriter": ["script", "script-brief"],
        "reviewer": ["script-review", "review"],
        "dzine_producer": ["assets", "dzine", "thumbnail"],
        "davinci_editor": ["manifest", "resolve", "render"],
        "publisher": ["tts", "publish", "youtube"],
    }

    components = agent_components.get(agent, [agent])
    events = _load_all_events(_path)

    return [
        e for e in events
        if e.get("component", "") in components
    ]


def get_promotion_candidates(
    *,
    threshold: int = 2,
    _path: Path | None = None,
) -> list[dict]:
    """Find events that have been applied enough times for SOUL promotion.

    Groups events by root_cause and returns those exceeding threshold.
    """
    events = _load_all_events(_path)
    applied = [e for e in events if e.get("status") in ("applied", "verified")]

    groups: dict[str, list[dict]] = defaultdict(list)
    for e in applied:
        key = e.get("root_cause", "unknown")
        groups[key].append(e)

    candidates = []
    for root_cause, items in groups.items():
        if len(items) >= threshold:
            candidates.append({
                "root_cause": root_cause,
                "count": len(items),
                "components": sorted({i.get("component", "") for i in items}),
                "severities": sorted({i.get("severity", "") for i in items}),
                "fix": items[0].get("fix_applied", ""),
                "events": [i.get("event_id", "") for i in items],
            })

    return sorted(candidates, key=lambda c: c["count"], reverse=True)


def get_weekly_summary(date: str = "", *, _path: Path | None = None) -> dict | None:
    """Load a weekly report by date (YYYY-MM-DD). Latest if no date given."""
    if not REPORTS_DIR.is_dir():
        return None

    if date:
        report_path = REPORTS_DIR / f"weekly-{date}.json"
        if report_path.is_file():
            return json.loads(report_path.read_text(encoding="utf-8"))
        return None

    # Find latest
    reports = sorted(REPORTS_DIR.glob("weekly-*.json"), reverse=True)
    if not reports:
        return None
    return json.loads(reports[0].read_text(encoding="utf-8"))
