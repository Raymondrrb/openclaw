"""Persistent cross-video error log.

Accumulates pipeline errors across all video runs in a single JSON file,
with resolution tracking and recurring-pattern detection.

Data file: data/error_log.json (append-only JSON array, created on first error).
Stdlib only.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

from tools.lib.common import now_iso, project_root

ERROR_LOG_PATH: Path = project_root() / "data" / "error_log.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_log(path: Path | None = None) -> list[dict]:
    """Read the error log, returning [] on missing/corrupt file."""
    p = path or ERROR_LOG_PATH
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _write_log(entries: list[dict], path: Path | None = None) -> None:
    """Write the full log atomically."""
    p = path or ERROR_LOG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
                 encoding="utf-8")


def _make_id(timestamp: str, error: str, salt: str = "") -> str:
    """Generate a unique error ID: e-<ts_short>-<5-char hash>."""
    ts_short = timestamp[:19].replace("-", "").replace(":", "").replace("T", "T")
    h = hashlib.sha256(f"{timestamp}{error}{salt}".encode()).hexdigest()[:5]
    return f"e-{ts_short}-{h}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_error(
    video_id: str,
    stage: str,
    error: str,
    *,
    exit_code: int = 1,
    context: dict | None = None,
    _path: Path | None = None,
) -> dict:
    """Append an error entry and return it."""
    ts = now_iso()
    entries = _read_log(_path)
    entry = {
        "id": _make_id(ts, error, f"{video_id}{len(entries)}"),
        "video_id": video_id,
        "timestamp": ts,
        "stage": stage,
        "exit_code": exit_code,
        "error": error,
        "context": context or {},
        "resolved": False,
        "resolution": None,
    }
    entries.append(entry)
    _write_log(entries, _path)
    return entry


def resolve_error(
    error_id: str,
    root_cause: str,
    fix: str,
    *,
    _path: Path | None = None,
) -> dict | None:
    """Mark an error resolved. Returns updated entry or None if not found."""
    entries = _read_log(_path)
    for entry in entries:
        if entry["id"] == error_id:
            entry["resolved"] = True
            entry["resolution"] = {
                "resolved_at": now_iso(),
                "root_cause": root_cause,
                "fix": fix,
            }
            _write_log(entries, _path)
            # Supabase: sync lesson
            try:
                from tools.lib.supabase_pipeline import save_lesson
                save_lesson(
                    entry.get("stage", "unknown"),
                    entry.get("error", "")[:80],
                    f"{root_cause} -> {fix}",
                    example={"video_id": entry.get("video_id", ""),
                             "error_id": error_id},
                )
            except Exception:
                pass
            return entry
    return None


def get_unresolved(
    *,
    stage: str = "",
    video_id: str = "",
    _path: Path | None = None,
) -> list[dict]:
    """Return unresolved errors, optionally filtered by stage/video."""
    entries = _read_log(_path)
    result = [e for e in entries if not e.get("resolved")]
    if stage:
        result = [e for e in result if e.get("stage") == stage]
    if video_id:
        result = [e for e in result if e.get("video_id") == video_id]
    return result


def get_patterns(
    *,
    min_count: int = 2,
    _path: Path | None = None,
) -> list[dict]:
    """Group errors by (stage, error[:80]) and return recurring patterns."""
    entries = _read_log(_path)
    groups: dict[tuple[str, str], list[dict]] = {}
    for e in entries:
        key = (e.get("stage", ""), e.get("error", "")[:80])
        groups.setdefault(key, []).append(e)

    patterns = []
    for (stage, pattern), items in sorted(groups.items()):
        if len(items) < min_count:
            continue
        patterns.append({
            "stage": stage,
            "pattern": pattern,
            "count": len(items),
            "unresolved": sum(1 for i in items if not i.get("resolved")),
            "video_ids": sorted({i["video_id"] for i in items}),
            "last_seen": max(i["timestamp"] for i in items),
        })
    return sorted(patterns, key=lambda p: p["count"], reverse=True)


def get_lessons(
    *,
    _path: Path | None = None,
) -> list[dict]:
    """Extract lessons from resolved errors.

    Groups resolved errors by (stage, error[:80]), deduplicates, and returns
    the most recent resolution per pattern.
    """
    entries = _read_log(_path)
    resolved = [e for e in entries if e.get("resolved") and e.get("resolution")]

    groups: dict[tuple[str, str], list[dict]] = {}
    for e in resolved:
        key = (e.get("stage", ""), e.get("error", "")[:80])
        groups.setdefault(key, []).append(e)

    lessons = []
    for (stage, pattern), items in sorted(groups.items()):
        latest = max(items, key=lambda i: i.get("resolution", {}).get("resolved_at", ""))
        res = latest["resolution"]
        lessons.append({
            "stage": stage,
            "pattern": pattern,
            "occurrences": len(items),
            "root_cause": res.get("root_cause", ""),
            "fix": res.get("fix", ""),
            "last_resolved": res.get("resolved_at", ""),
        })
    return sorted(lessons, key=lambda l: l["occurrences"], reverse=True)


def promote_to_learning(
    error_id: str,
    root_cause: str,
    fix: str,
    *,
    verification: str = "",
    severity: str = "FAIL",
    component: str = "",
    agent: str = "",
    _path: Path | None = None,
) -> dict | None:
    """Bridge: resolve error and create a LearningEvent in one call.

    Returns the created LearningEvent as dict, or None if error not found.
    """
    from tools.learning_event import promote_from_error
    event = promote_from_error(
        error_id,
        root_cause=root_cause,
        fix=fix,
        verification=verification,
        severity=severity,
        component=component,
        agent=agent,
        _error_path=_path,
    )
    if event is None:
        return None
    from dataclasses import asdict
    return asdict(event)


def get_stale(
    *,
    days: int = 7,
    _path: Path | None = None,
) -> list[dict]:
    """Return unresolved errors older than *days*."""
    entries = _read_log(_path)
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=days)
    ).isoformat()

    return [
        e for e in entries
        if not e.get("resolved")
        and e.get("timestamp", "") < cutoff
    ]


def format_log_text(
    *,
    stage: str = "",
    video_id: str = "",
    show_resolved: bool = False,
    limit: int = 20,
    _path: Path | None = None,
) -> str:
    """Human-readable error log for CLI display."""
    entries = _read_log(_path)

    if not show_resolved:
        entries = [e for e in entries if not e.get("resolved")]
    if stage:
        entries = [e for e in entries if e.get("stage") == stage]
    if video_id:
        entries = [e for e in entries if e.get("video_id") == video_id]

    if not entries:
        return "No errors found."

    # Most recent first, capped at limit
    entries = list(reversed(entries))[:limit]

    lines = []
    for e in entries:
        status = "RESOLVED" if e.get("resolved") else "OPEN"
        ts = e.get("timestamp", "?")[:19]
        lines.append(
            f"[{status}] {e.get('video_id', '?')} | {e.get('stage', '?')} | "
            f"{e.get('error', '?')}"
        )
        lines.append(f"         {ts}  id={e.get('id', '?')}")
        if e.get("resolved") and e.get("resolution"):
            res = e["resolution"]
            lines.append(f"         Fix: {res.get('fix', '?')}")
    return "\n".join(lines)
