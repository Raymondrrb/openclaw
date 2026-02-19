"""Learning Event — model, CRUD, and immediate learning loop.

Every pipeline failure becomes a formal LearningEvent. Events are created
immediately during execution, applied to agent memory in real-time, and
synced to the skill graph — no deferred processing.

Data stores:
  - data/learning_events.json          (global append-only index)
  - artifacts/videos/<vid>/learning/events/<id>.json  (per-video)

Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tools.lib.common import now_iso, project_root

EVENTS_PATH: Path = project_root() / "data" / "learning_events.json"

# Valid values
SEVERITIES = ("INFO", "WARN", "FAIL", "BLOCKER")
STATUSES = ("open", "applied", "verified", "archived")


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

@dataclass
class LearningEvent:
    """A single learning captured from a pipeline run."""
    event_id: str
    run_id: str
    timestamp: str
    severity: str           # INFO | WARN | FAIL | BLOCKER
    component: str          # e.g. "dzine_producer", "research", "tts"
    symptom: str            # What went wrong (user-visible)
    root_cause: str         # Why it went wrong
    fix_applied: str        # What was done to fix it
    verification: str       # How we know the fix worked
    status: str = "open"    # open | applied | verified | archived
    video_id: str = ""
    source_error_id: str = ""   # Bridge from error_log
    promotion_rule: str = ""    # Rule text promoted to agent memory
    soul_update: str = ""       # Suggested SOUL file addition
    obsolete_rules_removed: list[str] = field(default_factory=list)


def _make_event_id(timestamp: str, symptom: str) -> str:
    """Generate unique event ID: le-<ts_compact>-<5-char hash>."""
    ts = timestamp[:19].replace("-", "").replace(":", "").replace("T", "T")
    h = hashlib.sha256(f"{timestamp}{symptom}".encode()).hexdigest()[:5]
    return f"le-{ts}-{h}"


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _read_events(path: Path | None = None) -> list[dict]:
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


def _write_events(entries: list[dict], path: Path | None = None) -> None:
    from rayvault.io import atomic_write_json
    p = path or EVENTS_PATH
    atomic_write_json(p, entries)


def _write_per_video(event: LearningEvent) -> None:
    """Write event to per-video learning directory."""
    if not event.video_id:
        return
    from rayvault.io import atomic_write_json
    vid_dir = (
        project_root() / "artifacts" / "videos" / event.video_id
        / "learning" / "events"
    )
    vid_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(vid_dir / f"{event.event_id}.json", asdict(event))


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_event(
    *,
    run_id: str,
    severity: str,
    component: str,
    symptom: str,
    root_cause: str,
    fix_applied: str,
    verification: str = "",
    video_id: str = "",
    source_error_id: str = "",
    agent: str = "",
    _path: Path | None = None,
) -> LearningEvent:
    """Create a learning event with IMMEDIATE learning loop.

    1. Persists event to global index + per-video dir
    2. Syncs to skill graph (creates learning node)
    3. Applies rule to agent memory (if agent specified)

    Returns the created LearningEvent.
    """
    if severity not in SEVERITIES:
        raise ValueError(f"Invalid severity {severity!r}, must be one of {SEVERITIES}")

    ts = now_iso()
    event = LearningEvent(
        event_id=_make_event_id(ts, symptom),
        run_id=run_id,
        timestamp=ts,
        severity=severity,
        component=component,
        symptom=symptom,
        root_cause=root_cause,
        fix_applied=fix_applied,
        verification=verification,
        video_id=video_id,
        source_error_id=source_error_id,
    )

    # Persist to global index
    entries = _read_events(_path)
    entries.append(asdict(event))
    _write_events(entries, _path)

    # Persist per-video
    _write_per_video(event)

    # --- IMMEDIATE LEARNING LOOP ---

    # Sync to skill graph
    try:
        sync_to_skill_graph(event)
    except Exception:
        pass  # Non-blocking

    # Apply to agent memory (if agent specified)
    if agent:
        try:
            from tools.learning_apply import apply_to_memory
            apply_to_memory(event, agent)
            event.status = "applied"
            event.promotion_rule = f"[{severity}] {component}: {root_cause} → {fix_applied}"
            # Update persisted event with new status
            _update_event_in_store(event, _path)
        except Exception:
            pass  # Non-blocking

    return event


def get_event(event_id: str, *, _path: Path | None = None) -> LearningEvent | None:
    """Retrieve a single event by ID."""
    for entry in _read_events(_path):
        if entry.get("event_id") == event_id:
            return _dict_to_event(entry)
    return None


def list_events(
    *,
    component: str = "",
    severity: str = "",
    video_id: str = "",
    status: str = "",
    _path: Path | None = None,
) -> list[LearningEvent]:
    """List events with optional filters."""
    entries = _read_events(_path)
    result = []
    for e in entries:
        if component and e.get("component") != component:
            continue
        if severity and e.get("severity") != severity:
            continue
        if video_id and e.get("video_id") != video_id:
            continue
        if status and e.get("status") != status:
            continue
        result.append(_dict_to_event(e))
    return result


def update_event(
    event_id: str,
    *,
    status: str = "",
    verification: str = "",
    soul_update: str = "",
    obsolete_rules_removed: list[str] | None = None,
    _path: Path | None = None,
) -> LearningEvent | None:
    """Update an existing event. Returns updated event or None."""
    entries = _read_events(_path)
    for entry in entries:
        if entry.get("event_id") == event_id:
            if status:
                if status not in STATUSES:
                    raise ValueError(f"Invalid status {status!r}")
                entry["status"] = status
            if verification:
                entry["verification"] = verification
            if soul_update:
                entry["soul_update"] = soul_update
            if obsolete_rules_removed is not None:
                entry["obsolete_rules_removed"] = obsolete_rules_removed
            _write_events(entries, _path)
            # Update per-video copy too
            evt = _dict_to_event(entry)
            _write_per_video(evt)
            return evt
    return None


def _update_event_in_store(event: LearningEvent, _path: Path | None = None) -> None:
    """Update an event's data in the global store."""
    entries = _read_events(_path)
    for i, entry in enumerate(entries):
        if entry.get("event_id") == event.event_id:
            entries[i] = asdict(event)
            _write_events(entries, _path)
            _write_per_video(event)
            return


def _dict_to_event(d: dict) -> LearningEvent:
    """Convert a dict to LearningEvent, handling missing fields gracefully."""
    return LearningEvent(
        event_id=d.get("event_id", ""),
        run_id=d.get("run_id", ""),
        timestamp=d.get("timestamp", ""),
        severity=d.get("severity", "INFO"),
        component=d.get("component", ""),
        symptom=d.get("symptom", ""),
        root_cause=d.get("root_cause", ""),
        fix_applied=d.get("fix_applied", ""),
        verification=d.get("verification", ""),
        status=d.get("status", "open"),
        video_id=d.get("video_id", ""),
        source_error_id=d.get("source_error_id", ""),
        promotion_rule=d.get("promotion_rule", ""),
        soul_update=d.get("soul_update", ""),
        obsolete_rules_removed=d.get("obsolete_rules_removed", []),
    )


# ---------------------------------------------------------------------------
# Skill graph sync
# ---------------------------------------------------------------------------

def sync_to_skill_graph(event: LearningEvent) -> Path | None:
    """Create a skill graph learning node from this event."""
    from tools.lib.skill_graph import record_learning

    tags = ["learning", "learning-event", event.severity.lower()]
    if event.component:
        tags.append(event.component)

    body = f"""## Symptom
{event.symptom}

## Root Cause
{event.root_cause}

## Fix Applied
{event.fix_applied}
"""
    if event.verification:
        body += f"""
## Verification
{event.verification}
"""

    return record_learning(
        title=f"[{event.severity}] {event.component}: {event.symptom[:60]}",
        description=f"{event.root_cause} → {event.fix_applied}",
        severity=event.severity.lower(),
        tags=tags,
        video_id=event.video_id,
        fix=event.fix_applied,
        body=body,
    )


# ---------------------------------------------------------------------------
# Bridge from error_log
# ---------------------------------------------------------------------------

def promote_from_error(
    error_id: str,
    *,
    root_cause: str,
    fix: str,
    verification: str = "",
    severity: str = "FAIL",
    component: str = "",
    agent: str = "",
    _error_path: Path | None = None,
    _events_path: Path | None = None,
) -> LearningEvent | None:
    """Bridge: resolve an error_log entry and create a LearningEvent.

    1. Calls error_log.resolve_error()
    2. Creates a LearningEvent linked via source_error_id
    """
    from tools.lib.error_log import resolve_error, _read_log

    # Resolve the error first
    resolved = resolve_error(error_id, root_cause, fix, _path=_error_path)
    if not resolved:
        return None

    return create_event(
        run_id=resolved.get("video_id", "unknown"),
        severity=severity,
        component=component or resolved.get("stage", "unknown"),
        symptom=resolved.get("error", ""),
        root_cause=root_cause,
        fix_applied=fix,
        verification=verification,
        video_id=resolved.get("video_id", ""),
        source_error_id=error_id,
        agent=agent,
        _path=_events_path,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    """Simple CLI for inspecting learning events."""
    import sys

    args = sys.argv[1:]
    if not args or args[0] == "list":
        events = list_events()
        if not events:
            print("No learning events found.")
            return
        print(f"Learning events: {len(events)}\n")
        for e in events:
            print(f"  [{e.severity}] {e.event_id} ({e.status})")
            print(f"    {e.component}: {e.symptom[:80]}")
            print(f"    Fix: {e.fix_applied[:80]}")
            print()

    elif args[0] == "get" and len(args) > 1:
        event = get_event(args[1])
        if event:
            print(json.dumps(asdict(event), indent=2))
        else:
            print(f"Event {args[1]} not found.")

    elif args[0] == "stats":
        events = list_events()
        by_sev = {}
        for e in events:
            by_sev[e.severity] = by_sev.get(e.severity, 0) + 1
        by_status = {}
        for e in events:
            by_status[e.status] = by_status.get(e.status, 0) + 1
        print(f"Total events: {len(events)}")
        print(f"By severity: {by_sev}")
        print(f"By status: {by_status}")

    else:
        print("Usage: python3 tools/learning_event.py [list|get EVENT_ID|stats]")


if __name__ == "__main__":
    _cli()
