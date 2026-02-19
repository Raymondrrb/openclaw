#!/usr/bin/env python3
"""Migration: convert existing resolved errors + skill graph learnings → LearningEvents.

Scans two sources:
  1. data/error_log.json — resolved errors → promote_from_error()
  2. agents/skills/learnings/*.md — manual nodes with severity+fix → create_event()

Idempotent: skips events whose source_error_id or symptom already exists.

Usage:
    python3 tools/migrate_errors_to_learning.py [--dry-run] [--verbose]
    python3 tools/migrate_errors_to_learning.py --apply

Stdlib only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import project_root
from tools.lib.error_log import _read_log
from tools.lib.skill_graph import _parse_frontmatter
from tools.learning_event import create_event, list_events, promote_from_error


# ---------------------------------------------------------------------------
# Source 1: Resolved errors from error_log
# ---------------------------------------------------------------------------

def _migrate_resolved_errors(*, dry_run: bool, verbose: bool) -> int:
    """Promote resolved error_log entries to learning events."""
    errors = _read_log()
    resolved = [e for e in errors if e.get("resolved") and e.get("resolution")]

    if not resolved:
        print(f"  error_log: 0 resolved errors to migrate")
        return 0

    # Get existing event source_error_ids to avoid duplicates
    existing = {e.source_error_id for e in list_events() if e.source_error_id}

    count = 0
    for entry in resolved:
        eid = entry.get("id", "")
        if eid in existing:
            if verbose:
                print(f"  [skip] already migrated: {eid}")
            continue

        res = entry.get("resolution", {})
        root_cause = res.get("root_cause", "")
        fix = res.get("fix", "")

        if not root_cause or not fix:
            if verbose:
                print(f"  [skip] incomplete resolution: {eid}")
            continue

        if dry_run:
            print(f"  [dry-run] would promote: {eid} | {entry.get('stage', '?')} | {entry.get('error', '?')[:60]}")
            count += 1
        else:
            evt = promote_from_error(
                eid,
                root_cause=root_cause,
                fix=fix,
                verification=f"Migrated from error_log resolution",
                severity="FAIL",
                component=entry.get("stage", "unknown"),
            )
            if evt:
                count += 1
                if verbose:
                    print(f"  [migrated] {eid} → {evt.event_id}")
            else:
                if verbose:
                    print(f"  [failed] could not promote: {eid}")

    return count


# ---------------------------------------------------------------------------
# Source 2: Skill graph manual learnings
# ---------------------------------------------------------------------------

_SEVERITY_MAP = {
    "critical": "BLOCKER",
    "blocker": "BLOCKER",
    "high": "FAIL",
    "fail": "FAIL",
    "medium": "WARN",
    "warn": "WARN",
    "low": "INFO",
    "info": "INFO",
}


def _migrate_skill_graph_learnings(*, dry_run: bool, verbose: bool) -> int:
    """Convert manual skill graph nodes (with severity+fix) to learning events."""
    learnings_dir = project_root() / "agents" / "skills" / "learnings"
    if not learnings_dir.is_dir():
        print(f"  skill_graph: learnings directory not found")
        return 0

    # Skip nodes already tagged as learning-event (created by sync_to_skill_graph)
    # Only process manual nodes that have severity + fix but aren't already events
    existing_symptoms = {e.symptom for e in list_events()}

    count = 0
    for md_file in sorted(learnings_dir.glob("*.md")):
        if md_file.name == "_index.md":
            continue

        text = md_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        tags = fm.get("tags", [])

        # Skip nodes already from the learning event system
        if "learning-event" in tags:
            continue

        severity_raw = fm.get("severity", "")
        fix = fm.get("fix", "")

        if not severity_raw:
            continue

        severity = _SEVERITY_MAP.get(severity_raw.lower(), "")
        if not severity:
            if verbose:
                print(f"  [skip] unknown severity '{severity_raw}': {md_file.name}")
            continue

        # Extract structured content from the markdown
        title = ""
        root_cause = ""
        symptom = ""
        verification = ""

        for line in text.split("\n"):
            line_s = line.strip()
            if line_s.startswith("# ") and not title:
                title = line_s[2:].strip()

        # Try to extract sections
        sections = _extract_sections(text)
        symptom = (
            sections.get("incident", "")
            or sections.get("symptom", "")
            or title
            or fm.get("description", "")[:80]
        )
        root_cause = sections.get("root cause", "") or sections.get("root_cause", "")
        fix = sections.get("fix applied", "") or sections.get("fix", "") or fix
        verification = sections.get("verification", "") or sections.get("prevention rule", "")

        if not symptom or not fix:
            if verbose:
                print(f"  [skip] missing symptom/fix: {md_file.name}")
            continue

        # Deduplicate by symptom
        if symptom in existing_symptoms:
            if verbose:
                print(f"  [skip] duplicate symptom: {md_file.name}")
            continue

        # Determine component from tags
        component = ""
        component_tags = {"assets", "dzine", "research", "script", "tts", "manifest", "thumbnail"}
        for tag in tags:
            if tag in component_tags:
                component = tag
                break

        video_id = fm.get("video_id", "")

        if dry_run:
            print(f"  [dry-run] would create: [{severity}] {component or '?'}: {symptom[:60]}")
            count += 1
        else:
            evt = create_event(
                run_id=f"migration-{md_file.stem}",
                severity=severity,
                component=component or "unknown",
                symptom=symptom[:200],
                root_cause=root_cause[:200] or "Extracted from skill graph learning",
                fix_applied=fix[:200],
                verification=verification[:200],
                video_id=video_id,
            )
            existing_symptoms.add(symptom)
            count += 1
            if verbose:
                print(f"  [migrated] {md_file.name} → {evt.event_id}")

    return count


def _extract_sections(text: str) -> dict[str, str]:
    """Extract markdown ## sections into a dict."""
    sections: dict[str, str] = {}
    current_key = ""
    current_lines: list[str] = []

    for line in text.split("\n"):
        if line.startswith("## "):
            if current_key:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line[3:].strip().lower()
            current_lines = []
        elif current_key:
            current_lines.append(line)

    if current_key:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate existing errors + skill graph learnings → LearningEvents",
    )
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Show what would be migrated (default)")
    parser.add_argument("--apply", action="store_true",
                        help="Actually perform the migration")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed progress")
    args = parser.parse_args()

    dry_run = not args.apply
    mode = "DRY RUN" if dry_run else "APPLY"

    print(f"\n{'='*50}")
    print(f"  Learning Events Migration ({mode})")
    print(f"{'='*50}\n")

    print("Source 1: Resolved errors from error_log")
    n_errors = _migrate_resolved_errors(dry_run=dry_run, verbose=args.verbose)

    print(f"\nSource 2: Manual skill graph learnings")
    n_learnings = _migrate_skill_graph_learnings(dry_run=dry_run, verbose=args.verbose)

    print(f"\n{'='*50}")
    if dry_run:
        print(f"  Would migrate: {n_errors} errors + {n_learnings} learnings")
        print(f"  Re-run with --apply to execute")
    else:
        print(f"  Migrated: {n_errors} errors + {n_learnings} learnings")
    print(f"{'='*50}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
