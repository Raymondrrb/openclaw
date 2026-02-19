# Closed-Loop Learning System

The learning system turns every pipeline failure into a formal event, applies it as an active rule in real-time, and periodically reviews rules for promotion to SOUL governance or tombstoning.

**SOUL > SKILL** — agents need governance (how they decide, prove, and react to errors) more than execution capabilities.

## Architecture

```
EXECUTE → FAIL → DIAGNOSE (immediate) → LEARN (immediate) → APPLY (immediate) → RETRY
                                                                     ↓
                                                             memory_active.json updated
                                                             skill graph node created
                                                             SOUL update suggested (if severe)

Periodic (weekly): REVISIT → tombstone obsolete → promote to SOUL → report
```

Learning happens **immediately during execution**. The weekly revisit is review, not learning.

## Modules

| Module               | Location                        | Purpose                                |
| -------------------- | ------------------------------- | -------------------------------------- |
| **learning_event**   | `tools/learning_event.py`       | Event model, CRUD, immediate loop      |
| **learning_apply**   | `tools/learning_apply.py`       | Agent memory management, tombstoning   |
| **learning_gate**    | `tools/learning_gate.py`        | Pipeline gate (4 checks)               |
| **learning_revisit** | `tools/learning_revisit.py`     | Weekly review + reports                |
| **registry**         | `rayvault/learning/registry.py` | Cross-video queries, pattern detection |

## Data Layout

```
data/
  learning_events.json              # Global append-only event index
  learning_reports/                  # Weekly reports (weekly-YYYY-MM-DD.json)
  error_log.json                    # Raw incident log (upstream)

state/agents/<agent_name>/
  memory_active.json                # Active rules driving decisions
  memory_archive/                   # Timestamped snapshots
  memory_tombstones.json            # Removed rules with evidence

artifacts/videos/<vid>/learning/
  events/<event_id>.json            # Per-video event files
```

## The Immediate Learning Loop

When `create_event()` is called:

1. **Persists** to `data/learning_events.json` + per-video directory
2. **Syncs** to skill graph via `record_learning()` (creates markdown node)
3. **Applies** rule to agent memory if `agent` parameter is provided

```python
from tools.learning_event import create_event

evt = create_event(
    run_id="v042-run-001",
    severity="FAIL",                    # INFO | WARN | FAIL | BLOCKER
    component="assets",
    symptom="Image hallucination in Product Background",
    root_cause="Changed reference angle from 3/4 to top-down",
    fix_applied="Reverted to original 3/4 angle",
    verification="Re-generated, product shape correct",
    video_id="v042",
    agent="dzine_producer",             # Triggers immediate memory apply
)
```

## Learning Gate

The gate runs 4 checks before each pipeline stage:

1. **check_diff_policies** — `policies.py` SHA changed since last run?
2. **check_diff_soul** — SOUL file for stage's agent changed?
3. **check_regressions** — unresolved FAIL/BLOCKER events for video+stage?
4. **check_known_failures** — recurring error patterns (3+ occurrences, unresolved)?

```python
from tools.learning_gate import learning_gate

result = learning_gate("v042", "assets")
if result.blocked:
    print(f"BLOCKED: {result.reason}")
    for check in result.checks:
        print(f"  [{check.name}] {'PASS' if check.passed else 'FAIL'}: {check.reason}")
```

Disable via `RAYVAULT_SKIP_LEARNING_GATE=1` or `LEARNING_GATE_ENABLED = False` in policies.py.

### Stage → Agent Mapping

| Stage         | Agent          |
| ------------- | -------------- |
| research      | researcher     |
| script        | scriptwriter   |
| script-brief  | scriptwriter   |
| script-review | reviewer       |
| assets        | dzine_producer |
| tts           | publisher      |
| manifest      | davinci_editor |
| day           | market_scout   |

## Agent Memory

Rules are stored per-agent at `state/agents/<name>/memory_active.json`:

```python
from tools.learning_apply import apply_to_memory, tombstone_rule, load_active_memory

# Apply a rule
rule = apply_to_memory(event, "dzine_producer")

# View active rules
memory = load_active_memory("dzine_producer")
for rule in memory.get("rules", []):
    print(f"[{rule['severity']}] {rule['rule']}")

# Tombstone an obsolete rule
tombstone_rule("dzine_producer", rule["rule_id"], "Superseded by new approach")
```

Max rules per agent: `LEARNING_MAX_ACTIVE_RULES_PER_AGENT` (default: 50). When exceeded, oldest non-critical rules are evicted. BLOCKER/FAIL rules survive eviction.

## Bridge from error_log

Resolved errors can be promoted to learning events:

```python
from tools.lib.error_log import promote_to_learning

# Resolve error and create learning event in one call
result = promote_to_learning(
    "e-20260219T120000-abc12",
    root_cause="No price validation",
    fix="Added price anomaly check",
    severity="FAIL",
    component="research",
    agent="researcher",
)
```

## Weekly Revisit

```bash
python3 tools/learning_revisit.py --scope all --days 7
python3 tools/learning_revisit.py --scope dzine_producer --days 14
```

4 phases:

1. **Revalidate** — flag stale rules (old + never re-applied) and conflicting rules
2. **Promotion scan** — find rules applied N+ times, suggest SOUL updates
3. **Weekly report** — aggregate metrics to `data/learning_reports/weekly-YYYY-MM-DD.json`
4. **Tombstone sweep** — archive old tombstones past grace period

## Migration

Convert existing skill graph learnings to formal events:

```bash
python3 tools/migrate_errors_to_learning.py --dry-run --verbose
python3 tools/migrate_errors_to_learning.py --apply
```

## Registry Queries

```python
from rayvault.learning.registry import (
    query_events, get_patterns, get_agent_learnings,
    get_promotion_candidates, get_weekly_summary,
)

# Cross-video search
events = query_events(component="assets", severity="FAIL")

# Recurring patterns
patterns = get_patterns(min_count=3)

# Events for an agent
learnings = get_agent_learnings("dzine_producer")

# SOUL promotion candidates
candidates = get_promotion_candidates(threshold=2)

# Latest weekly report
report = get_weekly_summary()
```

## CLI Tools

```bash
# List learning events
python3 tools/learning_event.py list
python3 tools/learning_event.py get EVENT_ID
python3 tools/learning_event.py stats

# View agent memory
python3 tools/learning_apply.py show dzine_producer
python3 tools/learning_apply.py tombstones dzine_producer
python3 tools/learning_apply.py init

# Run learning gate
python3 tools/learning_gate.py VIDEO_ID STAGE

# Weekly revisit
python3 tools/learning_revisit.py --scope all --days 7
```

## Policy Constants

All in `rayvault/policies.py`:

| Constant                                   | Default | Purpose                                  |
| ------------------------------------------ | ------- | ---------------------------------------- |
| `LEARNING_GATE_ENABLED`                    | `True`  | Master switch for the gate               |
| `LEARNING_REVISIT_INTERVAL_DAYS`           | `7`     | Revisit lookback period                  |
| `LEARNING_ARCHIVE_RETENTION_DAYS`          | `90`    | Archive retention                        |
| `LEARNING_MAX_ACTIVE_RULES_PER_AGENT`      | `50`    | Max rules before eviction                |
| `LEARNING_PROMOTION_THRESHOLD_OCCURRENCES` | `2`     | Min applications for SOUL promotion      |
| `LEARNING_TOMBSTONE_GRACE_DAYS`            | `30`    | Grace period before tombstone compaction |
