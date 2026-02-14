#!/usr/bin/env python3
"""RayVault Stats — Executive Logbook for RayviewsLab.

Compact, actionable health + efficiency report.
Primary: Supabase. Fallback: local JSONL logs.

Usage:
    python3 tools/rayvault_stats.py              # last 7 days
    python3 tools/rayvault_stats.py --days 1     # last 24h
    python3 tools/rayvault_stats.py --days 30    # last month
    python3 tools/rayvault_stats.py --json       # machine-readable
    python3 tools/rayvault_stats.py --failures   # gated/aborted runs
    python3 tools/rayvault_stats.py --product B0XXXXX  # drill down
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import statistics
from datetime import datetime, timezone, timedelta
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
_tools = Path(__file__).resolve().parent
if str(_tools) not in sys.path:
    sys.path.insert(0, str(_tools))

from tools.lib.common import load_env_file, project_root


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOCAL_LOGS_DIR = project_root() / "data" / "rayvault_logs"
RUNS_LOG = LOCAL_LOGS_DIR / "runs.jsonl"
EVENTS_LOG = LOCAL_LOGS_DIR / "events.jsonl"

CRITICAL_CLAIMS = {"price", "voltage", "compatibility", "core_specs"}
SCORE_BUCKETS = {"gold": 15.0, "silver": 12.0}  # >=15 gold, >=12 silver, <12 bronze

TOKEN_COST_PER_1K = float(os.environ.get("TOKEN_COST_PER_1K", "0.003"))


# ---------------------------------------------------------------------------
# Data loading — Supabase primary, local fallback
# ---------------------------------------------------------------------------

def _load_from_supabase(
    since: str,
    *,
    product_filter: str = "",
) -> tuple[list[dict], list[dict], list[dict], bool]:
    """Load runs, events, evidence from Supabase.

    Returns: (runs, events, evidence_items, online)
    """
    try:
        from tools.lib.supabase_client import query, _enabled
        if not _enabled():
            return [], [], [], False

        # Runs
        run_filters: dict[str, str] = {}
        if product_filter:
            run_filters["video_id"] = product_filter

        runs = query(
            "pipeline_runs",
            select="id,video_id,status,created_at,updated_at,context_snapshot,"
                   "policy_version,ranking_model,elapsed_ms,stages_completed",
            order="created_at.desc",
            limit=500,
        )
        # Filter by date in Python (PostgREST gte filter is less convenient)
        runs = [r for r in runs if r.get("created_at", "") >= since]
        if product_filter:
            runs = [r for r in runs if r.get("video_id", "") == product_filter]

        run_ids = [r["id"] for r in runs if "id" in r]

        # Events
        events = query(
            "run_events",
            select="run_id,event_type,action_id,payload,created_at",
            order="created_at.desc",
            limit=2000,
        )
        events = [e for e in events if e.get("run_id") in set(run_ids)]

        # Evidence (shared cache — fetched_at is canonical timestamp)
        evidence = query(
            "evidence_items",
            select="id,normalized_id,asin,claim_type,trust_tier,confidence,"
                   "value,value_hash,source_name,source_type,"
                   "reason_flags,fetched_at,expires_at",
            order="fetched_at.desc",
            limit=2000,
        )
        # Filter evidence by time window (not by run_id — it's a shared cache)
        evidence = [e for e in evidence if e.get("fetched_at", "") >= since]

        return runs, events, evidence, True

    except Exception as exc:
        print(f"[rayvault_stats] Supabase error: {exc}", file=sys.stderr)
        return [], [], [], False


def _load_from_local(
    since: str,
    *,
    product_filter: str = "",
) -> tuple[list[dict], list[dict], list[dict]]:
    """Load from local JSONL fallback."""
    runs = _read_jsonl(RUNS_LOG, since)
    events = _read_jsonl(EVENTS_LOG, since)
    if product_filter:
        runs = [r for r in runs if r.get("video_id", "") == product_filter]
        run_ids = {r.get("id", r.get("run_id", "")) for r in runs}
        events = [e for e in events if e.get("run_id") in run_ids]
    return runs, events, []


def _read_jsonl(path: Path, since: str) -> list[dict]:
    """Read a JSONL file, filtering by created_at >= since."""
    if not path.is_file():
        return []
    results = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if row.get("created_at", "") >= since:
                    results.append(row)
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return results


def write_local_log(table: str, row: dict) -> None:
    """Append a row to local JSONL (call alongside Supabase writes)."""
    LOCAL_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCAL_LOGS_DIR / f"{table}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def _detect_reputation_risks(evidence: list[dict]) -> list[dict]:
    """Find Tier 4/5 sources that disagree on the same product+claim.

    Groups evidence by (normalized_id or asin, claim_type), then checks
    if high-trust items (trust_tier >= 4) report distinct values.

    Returns list of:
        {product_id, claim_type, values: [{value, source, trust_tier}], severity}
    """
    # Group high-trust evidence by (product, claim)
    groups: dict[tuple[str, str], list[dict]] = {}
    for ev in evidence:
        tier = int(ev.get("trust_tier", 0))
        if tier < 4:
            continue
        product_id = ev.get("normalized_id") or ev.get("asin") or ""
        claim = ev.get("claim_type", "")
        if not product_id or not claim:
            continue
        groups.setdefault((product_id, claim), []).append(ev)

    risks: list[dict] = []
    for (product_id, claim), items in groups.items():
        # Dedupe values (stringify for comparison)
        value_map: dict[str, dict] = {}  # normalized_value → best item
        for item in items:
            raw = item.get("value")
            if raw is None:
                continue
            key = str(raw).strip().lower() if not isinstance(raw, dict) else json.dumps(raw, sort_keys=True)
            existing = value_map.get(key)
            if existing is None or int(item.get("trust_tier", 0)) > int(existing.get("trust_tier", 0)):
                value_map[key] = item

        if len(value_map) >= 2:
            severity = "critical" if claim in CRITICAL_CLAIMS else "warning"
            values = [
                {
                    "value": it.get("value"),
                    "source": it.get("source_name", ""),
                    "trust_tier": int(it.get("trust_tier", 0)),
                }
                for it in value_map.values()
            ]
            risks.append({
                "product_id": product_id,
                "claim_type": claim,
                "values": values,
                "severity": severity,
            })

    return risks


def compute_metrics(
    runs: list[dict],
    events: list[dict],
    evidence: list[dict],
) -> dict:
    """Compute all executive metrics from raw data."""
    total = len(runs)
    if total == 0:
        return {"total_runs": 0, "message": "No data for this period."}

    # --- Status breakdown ---
    by_status: dict[str, int] = {}
    for r in runs:
        s = r.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    done = by_status.get("done", 0) + by_status.get("complete", 0)
    gated = by_status.get("waiting_approval", 0)
    aborted = by_status.get("aborted", 0)
    failed = by_status.get("failed", 0)

    # --- Events breakdown ---
    event_types: dict[str, int] = {}
    gate_reasons: dict[str, int] = {}
    auto_refetch_count = 0
    auto_refetch_healed = 0

    for e in events:
        et = e.get("event_type", "")
        event_types[et] = event_types.get(et, 0) + 1

        if et == "cb_pause":
            payload = e.get("payload", {})
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {}
            reason = payload.get("gate_reason", "unknown")
            # Simplify reason
            if "price" in reason:
                gate_reasons["price"] = gate_reasons.get("price", 0) + 1
            elif "voltage" in reason:
                gate_reasons["voltage"] = gate_reasons.get("voltage", 0) + 1
            elif "compatibility" in reason:
                gate_reasons["compatibility"] = gate_reasons.get("compatibility", 0) + 1
            elif "core_specs" in reason:
                gate_reasons["core_specs"] = gate_reasons.get("core_specs", 0) + 1
            elif "missing" in reason.lower():
                gate_reasons["missing_claim"] = gate_reasons.get("missing_claim", 0) + 1
            elif "expired" in reason.lower():
                gate_reasons["expired"] = gate_reasons.get("expired", 0) + 1
            else:
                gate_reasons["other"] = gate_reasons.get("other", 0) + 1

        if et == "cb_auto_refetch":
            auto_refetch_count += 1
        if et == "cb_healed":
            auto_refetch_healed += 1

    # Count gate events (not just current status)
    total_gates = event_types.get("cb_pause", 0)

    # --- Autonomy ---
    runs_no_gate = total - total_gates
    autonomy_rate = (runs_no_gate / total * 100) if total > 0 else 0
    gate_rate = (total_gates / total * 100) if total > 0 else 0
    abort_rate = (aborted / total * 100) if total > 0 else 0
    refetch_success = (
        (auto_refetch_healed / auto_refetch_count * 100)
        if auto_refetch_count > 0 else 0
    )

    # --- Evidence scores ---
    scores_by_type: dict[str, list[float]] = {}
    all_scores: list[float] = []
    for ev in evidence:
        ct = ev.get("claim_type", "")
        score = float(ev.get("score", ev.get("confidence", 0)))
        if ct:
            scores_by_type.setdefault(ct, []).append(score)
        all_scores.append(score)

    avg_score = round(statistics.mean(all_scores), 1) if all_scores else 0
    score_by_claim = {
        ct: round(statistics.mean(vals), 1)
        for ct, vals in sorted(scores_by_type.items())
    }

    # Critical coverage: % of runs where ALL critical claims have evidence above threshold
    runs_with_evidence: dict[str, set[str]] = {}  # run_id → set of claim_types
    for ev in evidence:
        rid = ev.get("run_id", "")
        ct = ev.get("claim_type", "")
        score = float(ev.get("score", ev.get("confidence", 0)))
        if rid and ct in CRITICAL_CLAIMS and score >= 0.6:
            runs_with_evidence.setdefault(rid, set()).add(ct)

    runs_fully_covered = sum(
        1 for covered in runs_with_evidence.values()
        if covered >= CRITICAL_CLAIMS
    )
    critical_coverage = (runs_fully_covered / total * 100) if total > 0 else 0

    # Conflict rate (events)
    conflict_count = event_types.get("conflict_detected", 0)

    # Reputation Risk: Tier 4/5 sources disagreeing on same product+claim
    reputation_risks = _detect_reputation_risks(evidence)

    # --- Score bucket ---
    score_bucket = "Gold" if avg_score >= SCORE_BUCKETS["gold"] else (
        "Silver" if avg_score >= SCORE_BUCKETS["silver"] else "Bronze"
    )

    # --- Tokens ---
    token_values: list[int] = []
    for r in runs:
        snapshot = r.get("context_snapshot", {})
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except json.JSONDecodeError:
                snapshot = {}
        tokens = snapshot.get("total_tokens", 0) or r.get("token_cost_est", 0)
        if tokens:
            token_values.append(int(tokens))

    token_median = int(statistics.median(token_values)) if token_values else 0
    token_p95 = int(sorted(token_values)[int(len(token_values) * 0.95)]) if len(token_values) >= 2 else token_median
    token_guard_status = "stable" if (token_p95 < token_median * 2.5 or token_p95 == 0) else "rising"

    cost_proxy = round(token_median / 1000 * TOKEN_COST_PER_1K, 4) if token_median else 0

    # --- Tone mix ---
    tone_high = 0
    tone_balanced = 0
    for r in runs:
        snapshot = r.get("context_snapshot", {})
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except json.JSONDecodeError:
                snapshot = {}
        tone = snapshot.get("tone_authority_level", "balanced")
        if tone == "high":
            tone_high += 1
        else:
            tone_balanced += 1

    tone_high_pct = round(tone_high / total * 100) if total > 0 else 0
    tone_balanced_pct = 100 - tone_high_pct

    return {
        "total_runs": total,
        "done": done,
        "gated": total_gates,
        "aborted": aborted,
        "failed": failed,
        "by_status": by_status,
        "trust_avg": avg_score,
        "trust_bucket": score_bucket,
        "score_by_claim": score_by_claim,
        "critical_coverage": round(critical_coverage, 1),
        "conflict_count": conflict_count,
        "autonomy_rate": round(autonomy_rate, 1),
        "gate_rate": round(gate_rate, 1),
        "abort_rate": round(abort_rate, 1),
        "auto_refetch_count": auto_refetch_count,
        "auto_refetch_success": round(refetch_success, 1),
        "gate_reasons": gate_reasons,
        "token_median": token_median,
        "token_p95": token_p95,
        "token_guard": token_guard_status,
        "cost_proxy": cost_proxy,
        "tone_high_pct": tone_high_pct,
        "tone_balanced_pct": tone_balanced_pct,
        "event_types": event_types,
        "reputation_risks": reputation_risks,
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report(
    metrics: dict,
    *,
    days: int = 7,
    online: bool = True,
    failures_only: bool = False,
    failed_runs: list[dict] | None = None,
) -> str:
    """Format metrics into a human-readable logbook report."""
    if metrics.get("total_runs", 0) == 0:
        return (
            f"RayviewsLab Logbook (Last {days} days)\n"
            + ("  [OFFLINE MODE]\n" if not online else "")
            + "  No data for this period.\n"
        )

    mode = "" if online else "  [OFFLINE MODE — using local logs]\n"

    m = metrics
    token_icon = "stable" if m["token_guard"] == "stable" else "RISING"

    lines = [
        f"RayviewsLab Logbook (Last {days} days)",
        mode.rstrip() if mode else None,
        "",
        f"  Runs: {m['total_runs']} total | Done: {m['done']} | Gated: {m['gated']} | Aborted: {m['aborted']}",
        f"  Trust Avg: {m['trust_avg']:.1f} ({m['trust_bucket']}) | Critical Coverage: {m['critical_coverage']:.0f}% | Conflicts: {m['conflict_count']} runs",
        f"  Autonomy: {m['autonomy_rate']:.0f}% | Auto-Refetch Success: {m['auto_refetch_success']:.0f}%",
        f"  Tokens/Run: median {m['token_median']:,} | p95 {m['token_p95']:,} | Token Guard: {token_icon}",
        f"  Cost Proxy: ~${m['cost_proxy']:.4f}/run",
        f"  Tone Mix: High {m['tone_high_pct']}% | Balanced {m['tone_balanced_pct']}%",
    ]

    # Top Issues
    gate_reasons = m.get("gate_reasons", {})
    if gate_reasons or m["conflict_count"] > 0:
        lines.append("")
        lines.append("Top Issues:")
        if gate_reasons:
            top_reason = max(gate_reasons, key=gate_reasons.get)
            lines.append(f"  - Most common Gate reason: {top_reason} ({gate_reasons[top_reason]} runs)")
        if m["conflict_count"] > 0:
            lines.append(f"  - High-trust conflicts detected: {m['conflict_count']} runs (reputation risk)")
        missing = gate_reasons.get("missing_claim", 0)
        if missing:
            lines.append(f"  - Missing critical claim: {missing} runs")

    # Reputation Risk — Tier 4/5 conflicts
    rep_risks = m.get("reputation_risks", [])
    if rep_risks:
        critical_risks = [r for r in rep_risks if r["severity"] == "critical"]
        warning_risks = [r for r in rep_risks if r["severity"] == "warning"]
        lines.append("")
        lines.append(f"Reputation Risks (Tier 4/5 Conflicts): {len(rep_risks)}")
        for r in critical_risks + warning_risks:
            tag = "CRITICAL" if r["severity"] == "critical" else "warn"
            vals = " vs ".join(
                f"{v['value']} ({v['source']}, T{v['trust_tier']})"
                for v in r["values"]
            )
            lines.append(f"  [{tag:>8s}] {r['product_id']} / {r['claim_type']}: {vals}")
        if critical_risks:
            lines.append(f"  -> Action: verify {len(critical_risks)} critical conflict(s) before publish")

    # Evidence by claim type
    if m.get("score_by_claim"):
        lines.append("")
        lines.append("Evidence by Claim:")
        for ct, avg in m["score_by_claim"].items():
            tier_label = "A" if ct in CRITICAL_CLAIMS else "B/C"
            lines.append(f"  - {ct} ({tier_label}): avg {avg:.1f}")

    # Actions / Recommendations
    actions = _generate_actions(m)
    if actions:
        lines.append("")
        lines.append("Actions:")
        for a in actions:
            lines.append(f"  - {a}")

    # Failures detail
    if failures_only and failed_runs:
        lines.append("")
        lines.append("Failed / Gated Runs:")
        for r in failed_runs[:20]:
            vid = r.get("video_id", "?")
            status = r.get("status", "?")
            ts = r.get("created_at", "")[:16]
            lines.append(f"  [{status:>18s}] {vid} @ {ts}")

    # Filter None values
    return "\n".join(line for line in lines if line is not None)


def _generate_actions(m: dict) -> list[str]:
    """Generate actionable recommendations from metrics."""
    actions = []

    if m["gate_rate"] > 50:
        actions.append(
            "Gate Rate >50%: consider increasing TTL or improving evidence collectors."
        )

    if m["autonomy_rate"] > 95 and m["conflict_count"] > 0:
        actions.append(
            "High autonomy + conflicts present: thresholds may be too loose."
        )

    rep_risks = m.get("reputation_risks", [])
    critical_risks = [r for r in rep_risks if r["severity"] == "critical"]
    if critical_risks:
        actions.append(
            f"{len(critical_risks)} reputation risk(s): Tier 4/5 sources disagree on critical claims. Do NOT publish without manual check."
        )

    if m["token_guard"] == "rising":
        actions.append(
            "Token usage rising: context packs may be too large. Tighten top_n."
        )

    if m["critical_coverage"] < 80:
        actions.append(
            f"Critical coverage at {m['critical_coverage']:.0f}%: some runs missing key claims."
        )

    if m["abort_rate"] > 20:
        actions.append(
            "Abort rate >20%: investigate common failure reasons."
        )

    if m["auto_refetch_count"] > 0 and m["auto_refetch_success"] < 50:
        actions.append(
            "Auto-refetch success <50%: evidence sources may be structurally low quality."
        )

    if not actions:
        actions.append("System healthy. No action required.")

    return actions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RayVault Stats — Executive Logbook",
    )
    parser.add_argument("--days", type=int, default=7, help="Time window in days (default: 7)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--failures", action="store_true", help="Show gated/aborted runs")
    parser.add_argument("--product", type=str, default="", help="Filter by product/video ID")
    args = parser.parse_args()

    # Load .env
    load_env_file()

    # Compute since date
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()

    # Load data — Supabase primary, local fallback
    runs, events, evidence, online = _load_from_supabase(
        since, product_filter=args.product,
    )

    if not online or not runs:
        local_runs, local_events, local_evidence = _load_from_local(
            since, product_filter=args.product,
        )
        if local_runs:
            runs = local_runs
            events = local_events
            evidence = local_evidence
            online = False

    # Compute metrics
    metrics = compute_metrics(runs, events, evidence)

    if args.json:
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
        return

    # Failed runs for --failures
    failed_runs = None
    if args.failures:
        failed_runs = [
            r for r in runs
            if r.get("status") in ("aborted", "failed", "waiting_approval")
        ]

    # Format and print
    report = format_report(
        metrics,
        days=args.days,
        online=online,
        failures_only=args.failures,
        failed_runs=failed_runs,
    )
    print(report)


if __name__ == "__main__":
    main()
