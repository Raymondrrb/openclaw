"""Learning Apply — agent memory management + tombstoning.

Manages per-agent active memory (rules driving decisions), archive
snapshots, and tombstoned rules. This is the "write" side of the
learning loop — events become rules, rules become governance.

Agent state lives at: state/agents/<agent_name>/
  memory_active.json     — active rules driving decisions
  memory_archive/        — timestamped snapshots
  memory_tombstones.json — removed rules with evidence

Stdlib only.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict
from pathlib import Path

from tools.lib.common import now_iso, project_root

AGENTS_STATE_DIR: Path = project_root() / "state" / "agents"

# Core agents (matching SOUL files)
CORE_AGENTS = (
    "market_scout",
    "researcher",
    "scriptwriter",
    "reviewer",
    "dzine_producer",
    "davinci_editor",
    "publisher",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _agent_dir(agent: str) -> Path:
    d = AGENTS_STATE_DIR / agent
    d.mkdir(parents=True, exist_ok=True)
    return d


def _active_path(agent: str) -> Path:
    return _agent_dir(agent) / "memory_active.json"


def _tombstones_path(agent: str) -> Path:
    return _agent_dir(agent) / "memory_tombstones.json"


def _archive_dir(agent: str) -> Path:
    d = _agent_dir(agent) / "memory_archive"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_json(path: Path) -> dict | list:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, data) -> None:
    from rayvault.io import atomic_write_json
    atomic_write_json(path, data)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_active_memory(agent: str) -> dict:
    """Load active memory rules for an agent.

    Returns dict: {"rules": [...], "updated": "...", "count": N}
    """
    path = _active_path(agent)
    data = _read_json(path)
    if not isinstance(data, dict):
        return {"rules": [], "updated": "", "count": 0}
    return data


def load_tombstones(agent: str) -> dict:
    """Load tombstoned rules for an agent.

    Returns dict: {"tombstones": [...], "count": N}
    """
    path = _tombstones_path(agent)
    data = _read_json(path)
    if not isinstance(data, dict):
        return {"tombstones": [], "count": 0}
    return data


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply_to_memory(event, agent: str) -> dict:
    """Apply a learning event as an active rule in agent memory.

    1. Archives current memory snapshot
    2. Adds new rule derived from event
    3. Enforces max rules limit (oldest non-critical dropped)

    Args:
        event: LearningEvent (or dict with same fields)
        agent: Agent name (e.g. "dzine_producer")

    Returns the new rule dict.
    """
    from rayvault.policies import LEARNING_MAX_ACTIVE_RULES_PER_AGENT

    # Normalize event to dict
    if hasattr(event, "__dataclass_fields__"):
        evt = asdict(event)
    elif isinstance(event, dict):
        evt = event
    else:
        raise TypeError(f"Expected LearningEvent or dict, got {type(event)}")

    # Archive current state before modifying
    archive_memory_snapshot(agent)

    # Build rule from event
    rule = {
        "rule_id": f"r-{evt.get('event_id', 'unknown')}",
        "source_event_id": evt.get("event_id", ""),
        "created": now_iso(),
        "severity": evt.get("severity", "INFO"),
        "component": evt.get("component", ""),
        "rule": f"{evt.get('root_cause', '')} → {evt.get('fix_applied', '')}",
        "symptom": evt.get("symptom", ""),
        "video_id": evt.get("video_id", ""),
        "applied_count": 1,
        "last_applied": now_iso(),
    }

    # Load current memory
    memory = load_active_memory(agent)
    rules = memory.get("rules", [])

    # Check for duplicate rules (same source event)
    for existing in rules:
        if existing.get("source_event_id") == rule["source_event_id"]:
            existing["applied_count"] = existing.get("applied_count", 1) + 1
            existing["last_applied"] = now_iso()
            memory["rules"] = rules
            memory["updated"] = now_iso()
            memory["count"] = len(rules)
            _write_json(_active_path(agent), memory)
            return existing

    # Add new rule
    rules.append(rule)

    # Enforce max rules limit
    if len(rules) > LEARNING_MAX_ACTIVE_RULES_PER_AGENT:
        # Remove oldest non-BLOCKER/FAIL rules first
        removable = [
            (i, r) for i, r in enumerate(rules)
            if r.get("severity") not in ("BLOCKER", "FAIL")
        ]
        if removable:
            idx, removed = removable[0]
            rules.pop(idx)

    memory["rules"] = rules
    memory["updated"] = now_iso()
    memory["count"] = len(rules)
    _write_json(_active_path(agent), memory)

    return rule


# ---------------------------------------------------------------------------
# Tombstone
# ---------------------------------------------------------------------------

def tombstone_rule(
    agent: str,
    rule_id: str,
    reason: str,
    *,
    evidence_ids: list[str] | None = None,
    superseded_by: str = "",
) -> dict | None:
    """Move a rule from active to tombstones.

    Returns the tombstoned rule dict, or None if rule not found.
    """
    # Archive before modifying
    archive_memory_snapshot(agent)

    memory = load_active_memory(agent)
    rules = memory.get("rules", [])

    # Find and remove rule
    removed = None
    new_rules = []
    for r in rules:
        if r.get("rule_id") == rule_id:
            removed = r
        else:
            new_rules.append(r)

    if removed is None:
        return None

    # Update active memory
    memory["rules"] = new_rules
    memory["updated"] = now_iso()
    memory["count"] = len(new_rules)
    _write_json(_active_path(agent), memory)

    # Add to tombstones
    tombstone = {
        **removed,
        "tombstoned_at": now_iso(),
        "reason": reason,
        "evidence_ids": evidence_ids or [],
        "superseded_by": superseded_by,
    }

    tombstones_data = load_tombstones(agent)
    tombstones_list = tombstones_data.get("tombstones", [])
    tombstones_list.append(tombstone)
    tombstones_data["tombstones"] = tombstones_list
    tombstones_data["count"] = len(tombstones_list)
    _write_json(_tombstones_path(agent), tombstones_data)

    return tombstone


# ---------------------------------------------------------------------------
# SOUL suggestion
# ---------------------------------------------------------------------------

def suggest_soul_update(agent: str, event) -> str:
    """Generate a suggested SOUL file addition from a learning event.

    Does NOT modify the SOUL file — returns a string diff for human review.
    """
    if hasattr(event, "__dataclass_fields__"):
        evt = asdict(event)
    elif isinstance(event, dict):
        evt = event
    else:
        return ""

    soul_name = f"SOUL_{agent}"
    soul_path = project_root() / "agents" / "team" / f"{soul_name}.md"
    if not soul_path.is_file():
        return f"# SOUL file not found: {soul_path}"

    severity = evt.get("severity", "")
    component = evt.get("component", "")
    root_cause = evt.get("root_cause", "")
    fix = evt.get("fix_applied", "")
    symptom = evt.get("symptom", "")

    suggestion = f"""## Suggested SOUL Update for {soul_name}

### Add to "Known Failure Patterns" section:

- **{symptom[:80]}**
  - Root cause: {root_cause}
  - Fix: {fix}
  - Severity: {severity}
  - Source: learning event {evt.get('event_id', 'N/A')}
  - Video: {evt.get('video_id', 'N/A')}

### Suggested rule text:
> When {component} encounters "{symptom[:60]}", apply: {fix}
"""
    return suggestion


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

def archive_memory_snapshot(agent: str) -> Path | None:
    """Create a timestamped snapshot of current active memory.

    Returns path to snapshot, or None if nothing to archive.
    """
    active_path = _active_path(agent)
    if not active_path.is_file():
        return None

    archive = _archive_dir(agent)
    ts = time.strftime("%Y%m%dT%H%M%S")
    snapshot_path = archive / f"memory_{ts}.json"

    # Don't archive if file is empty/minimal
    try:
        data = json.loads(active_path.read_text(encoding="utf-8"))
        if not data.get("rules"):
            return None
    except (json.JSONDecodeError, OSError):
        return None

    shutil.copy2(str(active_path), str(snapshot_path))
    return snapshot_path


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def init_agent_state(agent: str) -> None:
    """Initialize state directory for an agent (idempotent)."""
    _agent_dir(agent)
    active = _active_path(agent)
    if not active.is_file():
        _write_json(active, {"rules": [], "updated": now_iso(), "count": 0})
    tombstones = _tombstones_path(agent)
    if not tombstones.is_file():
        _write_json(tombstones, {"tombstones": [], "count": 0})


def init_all_agents() -> None:
    """Initialize state directories for all core agents."""
    for agent in CORE_AGENTS:
        init_agent_state(agent)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    import sys

    args = sys.argv[1:]
    if not args:
        print("Usage: python3 tools/learning_apply.py [init|show AGENT|tombstones AGENT]")
        return

    if args[0] == "init":
        init_all_agents()
        print(f"Initialized state for {len(CORE_AGENTS)} agents: {', '.join(CORE_AGENTS)}")

    elif args[0] == "show" and len(args) > 1:
        agent = args[1]
        memory = load_active_memory(agent)
        rules = memory.get("rules", [])
        print(f"Active memory for {agent}: {len(rules)} rules")
        for r in rules:
            print(f"  [{r.get('severity', '?')}] {r.get('rule_id', '?')}")
            print(f"    {r.get('rule', '?')}")
            print(f"    applied: {r.get('applied_count', 0)}x, last: {r.get('last_applied', '?')}")
            print()

    elif args[0] == "tombstones" and len(args) > 1:
        agent = args[1]
        data = load_tombstones(agent)
        tombstones = data.get("tombstones", [])
        print(f"Tombstones for {agent}: {len(tombstones)} rules")
        for t in tombstones:
            print(f"  {t.get('rule_id', '?')} — {t.get('reason', '?')}")
            print(f"    was: {t.get('rule', '?')}")
            print()

    else:
        print("Usage: python3 tools/learning_apply.py [init|show AGENT|tombstones AGENT]")


if __name__ == "__main__":
    _cli()
