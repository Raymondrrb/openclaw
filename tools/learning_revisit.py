#!/usr/bin/env python3
"""Learning Revisit — periodic review of active rules and events.

CLI: python3 tools/learning_revisit.py [--scope all|agent_name] [--days 7]

Phases:
  1. Revalidate active rules (flag stale/conflicting)
  2. Scan for promotable patterns (events applied N+ times → suggest SOUL update)
  3. Generate weekly report (data/learning_reports/weekly-YYYY-MM-DD.json)
  4. Tombstone sweep (compact old tombstones into archive)

The revisit is REVIEW, not learning. Learning is immediate (in create_event).
This job verifies rules are still valid, suggests promotions, and cleans up.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from tools.lib.common import now_iso, project_root
from tools.learning_apply import (
    CORE_AGENTS,
    load_active_memory,
    load_tombstones,
    suggest_soul_update,
    tombstone_rule,
)
from tools.learning_event import list_events, update_event


REPORTS_DIR = project_root() / "data" / "learning_reports"


# ---------------------------------------------------------------------------
# Phase 1: Revalidate active rules
# ---------------------------------------------------------------------------

def phase_revalidate(agent: str, days: int) -> dict:
    """Check active rules for staleness and conflicts.

    A rule is stale if:
    - It was created > days ago and never applied (applied_count == 1)
    - Its source event is now archived
    """
    import datetime

    memory = load_active_memory(agent)
    rules = memory.get("rules", [])
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=days)
    ).isoformat()

    stale = []
    conflicting = []

    for rule in rules:
        created = rule.get("created", "")
        applied_count = rule.get("applied_count", 1)

        # Stale: old and never re-applied
        if created < cutoff and applied_count <= 1:
            stale.append(rule)

        # Conflicting: same component, contradictory rules
        for other in rules:
            if other is rule:
                continue
            if (other.get("component") == rule.get("component")
                    and other.get("severity") != rule.get("severity")):
                if rule not in conflicting:
                    conflicting.append(rule)

    return {
        "agent": agent,
        "total_rules": len(rules),
        "stale": [r.get("rule_id") for r in stale],
        "conflicting": [r.get("rule_id") for r in conflicting],
    }


# ---------------------------------------------------------------------------
# Phase 2: Scan for promotable patterns
# ---------------------------------------------------------------------------

def phase_promotion_scan(agent: str) -> dict:
    """Find rules applied frequently enough for SOUL promotion."""
    from rayvault.policies import LEARNING_PROMOTION_THRESHOLD_OCCURRENCES

    memory = load_active_memory(agent)
    rules = memory.get("rules", [])

    candidates = []
    for rule in rules:
        if rule.get("applied_count", 0) >= LEARNING_PROMOTION_THRESHOLD_OCCURRENCES:
            # Generate SOUL suggestion
            event_id = rule.get("source_event_id", "")
            from tools.learning_event import get_event
            event = get_event(event_id) if event_id else None
            suggestion = ""
            if event:
                suggestion = suggest_soul_update(agent, event)

            candidates.append({
                "rule_id": rule.get("rule_id"),
                "rule": rule.get("rule"),
                "applied_count": rule.get("applied_count"),
                "severity": rule.get("severity"),
                "suggestion": suggestion[:200] if suggestion else "",
            })

    return {
        "agent": agent,
        "candidates": candidates,
    }


# ---------------------------------------------------------------------------
# Phase 3: Generate weekly report
# ---------------------------------------------------------------------------

def phase_weekly_report(scope: str, days: int) -> dict:
    """Generate aggregated weekly metrics."""
    import datetime

    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=days)
    ).isoformat()

    all_events = list_events()
    recent = [e for e in all_events if e.timestamp >= cutoff]

    by_severity = {}
    by_component = {}
    by_status = {}
    for e in recent:
        by_severity[e.severity] = by_severity.get(e.severity, 0) + 1
        by_component[e.component] = by_component.get(e.component, 0) + 1
        by_status[e.status] = by_status.get(e.status, 0) + 1

    agents_to_check = CORE_AGENTS if scope == "all" else (scope,)

    agent_summaries = {}
    for agent in agents_to_check:
        memory = load_active_memory(agent)
        tombstones = load_tombstones(agent)
        agent_summaries[agent] = {
            "active_rules": memory.get("count", 0),
            "tombstones": tombstones.get("count", 0),
        }

    report = {
        "generated_at": now_iso(),
        "period_days": days,
        "scope": scope,
        "events_total": len(all_events),
        "events_recent": len(recent),
        "by_severity": by_severity,
        "by_component": by_component,
        "by_status": by_status,
        "agent_summaries": agent_summaries,
    }

    # Write report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = time.strftime("%Y-%m-%d")
    report_path = REPORTS_DIR / f"weekly-{date_str}.json"
    from rayvault.io import atomic_write_json
    atomic_write_json(report_path, report)

    return report


# ---------------------------------------------------------------------------
# Phase 4: Tombstone sweep
# ---------------------------------------------------------------------------

def phase_tombstone_sweep(agent: str, grace_days: int) -> dict:
    """Compact old tombstones that exceed grace period."""
    import datetime

    from rayvault.policies import LEARNING_TOMBSTONE_GRACE_DAYS
    grace = grace_days or LEARNING_TOMBSTONE_GRACE_DAYS

    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=grace)
    ).isoformat()

    data = load_tombstones(agent)
    tombstones = data.get("tombstones", [])

    kept = []
    archived = []
    for t in tombstones:
        if t.get("tombstoned_at", "") < cutoff:
            archived.append(t)
        else:
            kept.append(t)

    if archived:
        # Write compacted tombstones
        data["tombstones"] = kept
        data["count"] = len(kept)
        from rayvault.io import atomic_write_json
        from tools.learning_apply import _tombstones_path, _archive_dir
        atomic_write_json(_tombstones_path(agent), data)

        # Write archived to dated file
        archive_dir = _archive_dir(agent)
        date_str = time.strftime("%Y%m%d")
        atomic_write_json(
            archive_dir / f"tombstones_archive_{date_str}.json",
            archived,
        )

    return {
        "agent": agent,
        "kept": len(kept),
        "archived": len(archived),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_revisit(scope: str = "all", days: int = 7) -> dict:
    """Run all 4 revisit phases."""
    agents = list(CORE_AGENTS) if scope == "all" else [scope]

    results = {
        "scope": scope,
        "days": days,
        "timestamp": now_iso(),
        "revalidation": {},
        "promotions": {},
        "tombstone_sweep": {},
        "report": None,
    }

    # Phase 1 + 2 + 4 per agent
    for agent in agents:
        results["revalidation"][agent] = phase_revalidate(agent, days)
        results["promotions"][agent] = phase_promotion_scan(agent)
        results["tombstone_sweep"][agent] = phase_tombstone_sweep(agent, days)

    # Phase 3: weekly report
    results["report"] = phase_weekly_report(scope, days)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Learning revisit — periodic rule review")
    parser.add_argument("--scope", default="all", help="Agent name or 'all'")
    parser.add_argument("--days", type=int, default=7, help="Look-back period in days")
    args = parser.parse_args()

    print(f"Running revisit: scope={args.scope}, days={args.days}")
    results = run_revisit(args.scope, args.days)

    # Print summary
    for agent, reval in results["revalidation"].items():
        stale = len(reval.get("stale", []))
        conflicts = len(reval.get("conflicting", []))
        total = reval.get("total_rules", 0)
        print(f"  {agent}: {total} rules, {stale} stale, {conflicts} conflicting")

    for agent, promo in results["promotions"].items():
        candidates = len(promo.get("candidates", []))
        if candidates:
            print(f"  {agent}: {candidates} SOUL promotion candidate(s)")

    for agent, sweep in results["tombstone_sweep"].items():
        archived = sweep.get("archived", 0)
        if archived:
            print(f"  {agent}: {archived} tombstones archived")

    report = results.get("report", {})
    if report:
        print(f"\nWeekly report: {report.get('events_recent', 0)} recent events "
              f"(of {report.get('events_total', 0)} total)")
        print(f"Report saved to: {REPORTS_DIR}/weekly-{time.strftime('%Y-%m-%d')}.json")


if __name__ == "__main__":
    main()
