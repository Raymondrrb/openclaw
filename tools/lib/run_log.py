"""Persistent pipeline run log.

Tracks every pipeline command execution — successful or not — in a single
append-only JSON file. Gives visibility into what ran, how long it took,
and which videos progressed.

Data file: data/run_log.json (append-only JSON array, created on first log).
Stdlib only.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.lib.common import now_iso, project_root

RUN_LOG_PATH: Path = project_root() / "data" / "run_log.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_log(path: Path | None = None) -> list[dict]:
    """Read the run log, returning [] on missing/corrupt file."""
    p = path or RUN_LOG_PATH
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
    p = path or RUN_LOG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
                 encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_run(
    video_id: str,
    command: str,
    exit_code: int,
    duration_s: float,
    *,
    niche: str = "",
    _path: Path | None = None,
) -> dict:
    """Append a run entry and return it."""
    entry = {
        "video_id": video_id,
        "command": command,
        "timestamp": now_iso(),
        "exit_code": exit_code,
        "duration_s": duration_s,
        "niche": niche,
    }
    entries = _read_log(_path)
    entries.append(entry)
    _write_log(entries, _path)
    return entry


def get_runs(
    *,
    video_id: str = "",
    command: str = "",
    since: str = "",
    limit: int = 50,
    _path: Path | None = None,
) -> list[dict]:
    """Return run entries, optionally filtered."""
    entries = _read_log(_path)
    if video_id:
        entries = [e for e in entries if e.get("video_id") == video_id]
    if command:
        entries = [e for e in entries if e.get("command") == command]
    if since:
        entries = [e for e in entries if e.get("timestamp", "") >= since]
    return entries[-limit:]


def format_runs_text(
    *,
    video_id: str = "",
    command: str = "",
    since: str = "",
    limit: int = 20,
    _path: Path | None = None,
) -> str:
    """Human-readable run log for CLI display."""
    runs = get_runs(
        video_id=video_id, command=command, since=since,
        limit=limit, _path=_path,
    )
    if not runs:
        return "No runs recorded."

    lines = []
    for r in reversed(runs):
        ok = "OK" if r.get("exit_code", 1) == 0 else f"EXIT {r.get('exit_code', '?')}"
        ts = r.get("timestamp", "?")[:19]
        vid = r.get("video_id", "?")
        cmd = r.get("command", "?")
        dur = r.get("duration_s", 0)
        niche = r.get("niche", "")
        niche_part = f"  ({niche})" if niche else ""
        lines.append(f"[{ok:>6s}] {vid} | {cmd:<15s} | {dur:>7.1f}s | {ts}{niche_part}")
    return "\n".join(lines)


def get_daily_summary(
    *,
    date: str = "",
    _path: Path | None = None,
) -> dict:
    """Summarize runs for a given date (YYYY-MM-DD). Defaults to today."""
    if not date:
        date = now_iso()[:10]

    entries = _read_log(_path)
    day_entries = [e for e in entries if e.get("timestamp", "")[:10] == date]

    by_command: dict[str, dict] = {}
    videos_touched: set[str] = set()

    for e in day_entries:
        cmd = e.get("command", "unknown")
        vid = e.get("video_id", "")
        if vid:
            videos_touched.add(vid)

        if cmd not in by_command:
            by_command[cmd] = {"count": 0, "ok": 0, "failed": 0, "total_duration_s": 0.0}
        bucket = by_command[cmd]
        bucket["count"] += 1
        if e.get("exit_code", 1) == 0:
            bucket["ok"] += 1
        else:
            bucket["failed"] += 1
        bucket["total_duration_s"] += e.get("duration_s", 0)

    # Compute avg_duration_s per command
    for bucket in by_command.values():
        if bucket["count"] > 0:
            bucket["avg_duration_s"] = round(bucket["total_duration_s"] / bucket["count"], 1)
        else:
            bucket["avg_duration_s"] = 0.0
        del bucket["total_duration_s"]

    return {
        "date": date,
        "total_runs": len(day_entries),
        "by_command": by_command,
        "videos_touched": sorted(videos_touched),
    }
