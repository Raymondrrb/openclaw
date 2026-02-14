#!/usr/bin/env python3
"""RayVault Doctor — production health + forensic integrity checker.

Two connection strategies:
  1. Admin DB (DATABASE_URL or SUPABASE_DB_URL) — pg_catalog checks, data health
  2. Anon REST (SUPABASE_URL + SUPABASE_ANON_KEY) — RLS lockdown probes

Three check sections:
  SECURITY  — RLS read/write lockdown for anon/authenticated
  FORENSICS — FK RESTRICT, UNIQUE constraints, indexes, triggers
  DATA      — ghost runs, orphans, stale critical evidence + ingestion health

Surgical modes:
    python3 tools/rayvault_doctor.py               # full check (all sections)
    python3 tools/rayvault_doctor.py --quick        # forensics + indexes only
    python3 tools/rayvault_doctor.py --security     # RLS lockdown probes only
    python3 tools/rayvault_doctor.py --health       # data health only
    python3 tools/rayvault_doctor.py --health --days 14   # custom window
    python3 tools/rayvault_doctor.py --json         # machine-readable
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
_tools = Path(__file__).resolve().parent
if str(_tools) not in sys.path:
    sys.path.insert(0, str(_tools))

from tools.lib.common import load_env_file


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RLS_TABLES = ["run_events", "evidence_items", "run_evidence", "product_fingerprints"]

REQUIRED_INDEXES = {
    "idx_run_evidence_unique":          "UNIQUE(run_id, evidence_id)",
    "idx_evidence_tier4plus":           "partial: trust_tier >= 4",
    "idx_evidence_items_expires":       "expiration housekeeping",
    "idx_run_events_idempotent":        "UNIQUE(run_id, action_id)",
    "idx_evidence_nid_claim_fetched":   "conflict detection composite",
    "idx_evidence_items_fetched_at":    "stats temporal window",
    "idx_pipeline_runs_approval_nonce": "CAS lookup",
}

REQUIRED_TRIGGERS = [
    ("trg_pipeline_runs_updated_at", "pipeline_runs"),
    ("trg_evidence_items_updated_at", "evidence_items"),
    ("trg_product_fingerprints_updated_at", "product_fingerprints"),
]

CRITICAL_CLAIMS = ("price", "voltage", "compatibility", "core_specs")

# Thresholds
GHOST_RUN_HOURS = 48
STALE_WARN_RATIO = 0.30   # 30% expired → WARN
STALE_FAIL_RATIO = 0.50   # 50% expired (price) → FAIL

# Ingestion health thresholds (per claim type — niche products may have fewer specs)
INGESTION_MIN_7D: dict[str, int] = {
    "price": 10,
    "voltage": 3,
    "compatibility": 3,
    "core_specs": 3,
}
INGESTION_MIN_7D_DEFAULT = 10

# Per-claim staleness windows: how long before "no fresh evidence" = STALLED
# Price changes fast → 6h. Reviews update slowly → 24h. Specs rarely change → 72h.
INGESTION_STALE_HOURS: dict[str, int] = {
    "price": 6,
    "voltage": 72,
    "compatibility": 72,
    "core_specs": 72,
}
INGESTION_STALE_HOURS_DEFAULT = 24

# Ghost run escalation
GHOST_AUTOABORT_HOURS = 72  # suggest auto-abort after this
STUCK_RUNNING_HOURS = 6     # 'running' for this long → likely crashed

# Supply vs demand
MIN_EVIDENCE_PER_RUN = 3.0  # target evidence items per completed run

# Timezone: America/Sao_Paulo (DST-aware, not fixed UTC-3)
try:
    from zoneinfo import ZoneInfo
    _BRT = ZoneInfo("America/Sao_Paulo")
except ImportError:
    # Python < 3.9 fallback
    _BRT = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------------------
# DB connection helpers
# ---------------------------------------------------------------------------

def _get_admin_db():
    """Get admin DB connection (psycopg2). Returns (conn, None) or (None, error_msg)."""
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL", "")
    if not db_url:
        return None, "DATABASE_URL / SUPABASE_DB_URL not set"
    try:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(db_url)
        return conn, None
    except ImportError:
        return None, "psycopg2 not installed (pip install psycopg2-binary)"
    except Exception as exc:
        return None, f"Connection failed: {exc}"


def _sql(conn, sql: str) -> list[dict]:
    """Execute SQL and return rows as list of dicts."""
    import psycopg2.extras
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        if cur.description:
            return [dict(row) for row in cur.fetchall()]
        return []


def _anon_rest_request(
    path: str,
    *,
    method: str = "GET",
    body: dict | None = None,
) -> tuple[int, dict | list | str]:
    """Make a REST request to Supabase PostgREST using anon key.

    Returns (status_code, response_body).
    """
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not supabase_url or not anon_key:
        return 0, "SUPABASE_URL or SUPABASE_ANON_KEY not set"

    url = f"{supabase_url}/rest/v1/{path}"
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() if exc.fp else ""
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw
    except Exception as exc:
        return 0, str(exc)


# ---------------------------------------------------------------------------
# Check result builder
# ---------------------------------------------------------------------------

def _result(section: str, check: str, status: str, detail: str) -> dict:
    return {"section": section, "check": check, "status": status, "detail": detail}


def _dual_time(utc_now: datetime | None = None) -> str:
    """Format current time as 'YYYY-MM-DD HH:MM UTC (HH:MM BRT)'."""
    if utc_now is None:
        utc_now = datetime.now(timezone.utc)
    brt_now = utc_now.astimezone(_BRT)
    return f"{utc_now.strftime('%Y-%m-%d %H:%M')} UTC ({brt_now.strftime('%H:%M')} BRT)"


# ---------------------------------------------------------------------------
# SECURITY checks — RLS lockdown probes
# ---------------------------------------------------------------------------

def _probe_anon_op(
    label: str,
    path: str,
    *,
    method: str = "GET",
    body: dict | None = None,
    expect_rows: bool = True,
) -> dict:
    """Run a single anon REST probe. Returns a _result dict.

    For GET: FAIL if rows returned. PASS if 0 rows / 403 / 401.
    For POST/PATCH: FAIL if 2xx. PASS if 403 / 401 / other rejection.
    """
    status_code, resp = _anon_rest_request(path, method=method, body=body)

    if status_code == 0:
        return _result("SECURITY", label, "SKIP", f"Connection error: {resp}")

    if status_code in (401, 403):
        return _result("SECURITY", label, "PASS", f"Blocked ({status_code})")

    if method == "GET":
        if isinstance(resp, list) and len(resp) == 0:
            return _result("SECURITY", label, "PASS", "0 rows (RLS filtering active)")
        if isinstance(resp, list) and len(resp) > 0:
            return _result("SECURITY", label, "FAIL",
                           f"Returned {len(resp)} row(s) — anon can read data!")
        return _result("SECURITY", label, "PASS",
                       f"PostgREST returned {status_code} (blocked)")

    # POST / PATCH
    if 200 <= status_code < 300:
        return _result("SECURITY", label, "FAIL",
                       f"Anon {method} succeeded ({status_code}) — RLS broken!")
    return _result("SECURITY", label, "PASS", f"{method} rejected ({status_code})")


def check_security(*, quick: bool = False) -> list[dict]:
    """Probe RLS lockdown via anon REST client: SELECT, INSERT, UPDATE."""
    results = []
    supabase_url = os.environ.get("SUPABASE_URL", "")
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")

    if not supabase_url or not anon_key:
        for label in ("anon_select", "anon_select_filter", "anon_insert", "anon_update"):
            results.append(_result(
                "SECURITY", label, "SKIP",
                "SUPABASE_URL or SUPABASE_ANON_KEY not set",
            ))
        return results

    # S1 — SELECT (unfiltered): try to read pipeline_runs
    results.append(_probe_anon_op(
        "anon_select",
        "pipeline_runs?select=id&limit=1",
    ))

    # S2 — SELECT with filter (sometimes RLS blocks unfiltered but leaks with eq)
    results.append(_probe_anon_op(
        "anon_select_filter",
        "run_events?select=id,event_type&event_type=eq.error&limit=1",
    ))

    if quick:
        results.append(_result("SECURITY", "anon_insert", "SKIP", "Skipped in --quick mode"))
        results.append(_result("SECURITY", "anon_update", "SKIP", "Skipped in --quick mode"))
        return results

    # S3 — INSERT: try to create a run_event
    marker = f"doctor_probe_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    probe_body = {
        "run_id": "00000000-0000-0000-0000-000000000000",
        "action_id": marker,
        "event_type": "error",
        "payload": json.dumps({"probe": True}),
    }
    insert_result = _probe_anon_op(
        "anon_insert", "run_events", method="POST", body=probe_body,
    )
    results.append(insert_result)
    if insert_result["status"] == "FAIL":
        _cleanup_probe(marker)

    # S4 — UPDATE: try to patch an existing run_event
    update_result = _probe_anon_op(
        "anon_update",
        "run_events?event_type=eq.error&limit=1",
        method="PATCH",
        body={"payload": json.dumps({"probe_update": True})},
    )
    results.append(update_result)

    return results


def _cleanup_probe(marker: str) -> None:
    """Attempt to clean up a doctor probe that shouldn't have succeeded."""
    conn, err = _get_admin_db()
    if conn:
        try:
            _sql(conn, f"DELETE FROM public.run_events WHERE action_id = '{marker}'")
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# FORENSICS checks — catalog queries via admin DB
# ---------------------------------------------------------------------------

def check_forensics(conn) -> list[dict]:
    """Check constraints, indexes, triggers via pg_catalog."""
    results = []

    # F1: set_updated_at() function
    rows = _sql(conn, """
        select 1 from pg_proc
        where proname = 'set_updated_at'
          and pronamespace = 'public'::regnamespace;
    """)
    results.append(_result(
        "FORENSICS", "fn_set_updated_at",
        "PASS" if rows else "FAIL",
        "Function exists" if rows else "set_updated_at() missing — triggers will fail",
    ))

    # F2: RLS policies (catalog-level, WITH CHECK verification)
    policy_rows = _sql(conn, """
        select tablename, policyname, roles::text, qual, with_check
        from pg_policies
        where schemaname = 'public'
          and tablename in ('run_events', 'evidence_items', 'run_evidence', 'product_fingerprints')
        order by tablename, policyname;
    """)
    policy_map: dict[str, list[dict]] = {}
    for row in policy_rows:
        policy_map.setdefault(row["tablename"], []).append(row)

    for table in RLS_TABLES:
        policies = policy_map.get(table, [])
        anon_ok = auth_ok = False
        for p in policies:
            roles = str(p.get("roles", ""))
            qual = str(p.get("qual", "")).strip().lower()
            wc = str(p.get("with_check", "") or "").strip().lower()
            using_false = qual in ("false", "(false)")
            check_false = wc in ("false", "(false)")
            if "anon" in roles:
                anon_ok = using_false and check_false
            if "authenticated" in roles:
                auth_ok = using_false and check_false

        if anon_ok and auth_ok:
            results.append(_result(
                "FORENSICS", f"rls_policy_{table}", "PASS",
                "deny anon + authenticated (USING + WITH CHECK)",
            ))
        else:
            missing = []
            if not anon_ok:
                missing.append("anon")
            if not auth_ok:
                missing.append("authenticated")
            results.append(_result(
                "FORENSICS", f"rls_policy_{table}", "FAIL",
                f"Missing/broken deny policy for: {', '.join(missing)}",
            ))

    # F3: FK RESTRICT on run_evidence.evidence_id
    fk_rows = _sql(conn, """
        select c.conname, c.confdeltype
        from pg_constraint c
        join pg_attribute a on a.attrelid = c.conrelid
                           and a.attnum = any(c.conkey)
        where c.conrelid  = 'public.run_evidence'::regclass
          and c.confrelid = 'public.evidence_items'::regclass
          and c.contype   = 'f'
          and a.attname   = 'evidence_id';
    """)
    if not fk_rows:
        results.append(_result(
            "FORENSICS", "fk_evidence_restrict", "FAIL",
            "No FK found: run_evidence.evidence_id -> evidence_items.id",
        ))
    else:
        for row in fk_rows:
            dt = row["confdeltype"]
            name = row["conname"]
            if dt in ("r", "a"):
                label = "RESTRICT" if dt == "r" else "NO ACTION"
                results.append(_result(
                    "FORENSICS", "fk_evidence_restrict", "PASS",
                    f"{name}: ON DELETE {label} (forensic-safe)",
                ))
            else:
                action = {"c": "CASCADE", "n": "SET NULL", "d": "SET DEFAULT"}.get(dt, dt)
                results.append(_result(
                    "FORENSICS", "fk_evidence_restrict", "FAIL",
                    f"{name}: ON DELETE {action} — should be RESTRICT",
                ))

    # F4: UNIQUE(run_id, evidence_id)
    uniq_rows = _sql(conn, """
        select 1 from pg_indexes
        where schemaname = 'public'
          and indexname = 'idx_run_evidence_unique';
    """)
    results.append(_result(
        "FORENSICS", "unique_run_evidence",
        "PASS" if uniq_rows else "FAIL",
        "UNIQUE(run_id, evidence_id) exists" if uniq_rows else "UNIQUE constraint missing — duplicate evidence per run possible",
    ))

    # F5: Required indexes
    idx_names = list(REQUIRED_INDEXES.keys())
    idx_rows = _sql(conn, f"""
        select indexname, pg_get_expr(i.indpred, i.indrelid) as predicate
        from pg_indexes pi
        join pg_class c on c.relname = pi.indexname and c.relnamespace = 'public'::regnamespace
        join pg_index i on i.indexrelid = c.oid
        where pi.schemaname = 'public'
          and pi.indexname = any(array[{", ".join(f"'{n}'" for n in idx_names)}]);
    """)
    found_idx = {row["indexname"]: row.get("predicate") for row in idx_rows}

    for idx_name, desc in REQUIRED_INDEXES.items():
        if idx_name in found_idx:
            extra = ""
            if "partial" in desc and found_idx[idx_name]:
                extra = f" (partial: {found_idx[idx_name]})"
            elif "partial" in desc and not found_idx[idx_name]:
                extra = " (WARNING: expected partial but no predicate found)"
            results.append(_result("FORENSICS", f"idx_{idx_name}", "PASS", f"{desc}{extra}"))
        else:
            results.append(_result("FORENSICS", f"idx_{idx_name}", "FAIL", f"Missing: {desc}"))

    # F6: Audit trail population (run_evidence actually being written)
    audit_rows = _sql(conn, """
        select
            (select count(*) from public.pipeline_runs
             where status = 'done'
               and created_at > now() - interval '7 days') as runs_done_7d,
            (select count(*) from public.run_evidence
             where created_at > now() - interval '7 days') as re_rows_7d;
    """)
    if audit_rows:
        runs_done = int(audit_rows[0].get("runs_done_7d") or 0)
        re_rows = int(audit_rows[0].get("re_rows_7d") or 0)
        if runs_done > 0 and re_rows == 0:
            results.append(_result(
                "FORENSICS", "audit_trail_populated", "FAIL",
                f"No run_evidence rows in 7d but {runs_done} runs completed — audit trail missing",
            ))
        elif runs_done == 0:
            results.append(_result(
                "FORENSICS", "audit_trail_populated", "PASS",
                "No completed runs in 7d (nothing to audit)",
            ))
        else:
            ratio = round(re_rows / runs_done, 1)
            status = "PASS" if ratio >= MIN_EVIDENCE_PER_RUN else "WARN"
            detail = f"{re_rows} evidence rows / {runs_done} runs = {ratio}/run"
            if status == "WARN":
                detail += f" (target >= {MIN_EVIDENCE_PER_RUN})"
            results.append(_result("FORENSICS", "audit_trail_populated", status, detail))

    # F7: Triggers
    for trig_name, table_name in REQUIRED_TRIGGERS:
        trig_rows = _sql(conn, f"""
            select 1 from pg_trigger
            where tgname = '{trig_name}'
              and tgrelid = 'public.{table_name}'::regclass;
        """)
        results.append(_result(
            "FORENSICS", f"trigger_{trig_name}",
            "PASS" if trig_rows else "FAIL",
            f"on {table_name}" if trig_rows else f"Missing on {table_name}",
        ))

    return results


# ---------------------------------------------------------------------------
# DATA HEALTH checks
# ---------------------------------------------------------------------------

def check_data_health(conn, *, days: int = 7) -> list[dict]:
    """Check ghost runs, orphans, stale evidence + ingestion health."""
    results = []

    # D1: Ghost runs — waiting_approval > 48h + running > 6h (likely crashed)
    ghost_rows = _sql(conn, f"""
        select id, video_id, status,
               extract(epoch from (now() - created_at)) / 3600 as age_hours
        from public.pipeline_runs
        where (status = 'waiting_approval'
               and created_at < now() - interval '{GHOST_RUN_HOURS} hours')
           or (status in ('running', 'in_progress')
               and created_at < now() - interval '{STUCK_RUNNING_HOURS} hours')
        order by created_at
        limit 10;
    """)
    ghost_count = len(ghost_rows)
    if ghost_count == 0:
        results.append(_result(
            "DATA", "ghost_runs", "PASS",
            f"No stuck runs (waiting_approval > {GHOST_RUN_HOURS}h, running > {STUCK_RUNNING_HOURS}h)",
        ))
    else:
        detail_lines = [f"{ghost_count} stuck run(s):"]
        actions: list[str] = []
        for g in ghost_rows:
            vid = g.get("video_id", "?")
            age = int(g.get("age_hours", 0))
            rid = str(g.get("id", ""))[:8]
            st = g.get("status", "?")
            detail_lines.append(f"  {rid}... ({vid}) [{st}] — {age}h old")

            if st == "waiting_approval" and age > GHOST_AUTOABORT_HOURS:
                actions.append(f"auto-abort {rid}... ({age}h > {GHOST_AUTOABORT_HOURS}h limit)")
            elif st == "waiting_approval":
                actions.append(f"send Telegram reminder for {rid}...")
            elif st in ("running", "in_progress"):
                actions.append(f"mark {rid}... as failed (likely crashed after {age}h)")

        if actions:
            detail_lines.append("  Actions:")
            for a in actions:
                detail_lines.append(f"    -> {a}")

        results.append(_result("DATA", "ghost_runs", "WARN", "\n".join(detail_lines)))

    # D2: Orphan run_evidence (FK should prevent, but verify)
    orphan_rows = _sql(conn, """
        select count(*) as cnt from public.run_evidence re
        left join public.pipeline_runs r on r.id = re.run_id
        left join public.evidence_items e on e.id = re.evidence_id
        where r.id is null or e.id is null;
    """)
    orphan_count = int(orphan_rows[0]["cnt"]) if orphan_rows else 0
    if orphan_count == 0:
        results.append(_result("DATA", "orphan_run_evidence", "PASS", "No orphaned rows"))
    else:
        results.append(_result("DATA", "orphan_run_evidence", "FAIL", f"{orphan_count} orphaned row(s) — FK integrity broken"))

    # D3: Supply vs Demand — evidence capacity vs production volume
    supply_rows = _sql(conn, f"""
        select
            (select count(*) from public.pipeline_runs
             where status = 'done'
               and created_at > now() - interval '{days} days') as runs_done,
            (select count(distinct id) from public.evidence_items
             where created_at > now() - interval '{days} days') as evidence_created;
    """)
    if supply_rows:
        runs_done = int(supply_rows[0].get("runs_done") or 0)
        ev_created = int(supply_rows[0].get("evidence_created") or 0)
        if runs_done >= 3:
            avg = round(ev_created / runs_done, 1)
            if avg < MIN_EVIDENCE_PER_RUN:
                results.append(_result(
                    "DATA", "supply_vs_demand", "WARN",
                    f"evidence_per_run={avg} (target >= {MIN_EVIDENCE_PER_RUN}) "
                    f"— ingestion capacity low vs production demand "
                    f"({ev_created} evidence / {runs_done} runs in {days}d)",
                ))
            else:
                results.append(_result(
                    "DATA", "supply_vs_demand", "PASS",
                    f"evidence_per_run={avg} ({ev_created} evidence / {runs_done} runs in {days}d)",
                ))
        elif runs_done > 0:
            avg = round(ev_created / max(runs_done, 1), 1)
            results.append(_result(
                "DATA", "supply_vs_demand", "PASS",
                f"evidence_per_run={avg} ({ev_created} evidence / {runs_done} runs in {days}d) — too few runs to assess",
            ))
        else:
            results.append(_result(
                "DATA", "supply_vs_demand", "PASS",
                f"No completed runs in {days}d",
            ))

    # D4: Stale critical evidence + ingestion health + collector identification
    # Per-claim freshness windows (price 6h, specs 72h, default 24h)
    claims_sql = ", ".join(f"'{c}'" for c in CRITICAL_CLAIMS)
    fresh_case = " ".join(
        f"when '{ct}' then interval '{hrs} hours'"
        for ct, hrs in INGESTION_STALE_HOURS.items()
    )
    stale_rows = _sql(conn, f"""
        select
            claim_type,
            count(*) as total_window,
            count(*) filter (
                where expires_at is not null and expires_at < now()
            ) as expired_count,
            count(*) filter (
                where fetched_at > now() - (case claim_type {fresh_case}
                    else interval '{INGESTION_STALE_HOURS_DEFAULT} hours' end)
            ) as fresh_window,
            max(fetched_at) as last_fetched_at,
            extract(epoch from (now() - max(fetched_at))) / 3600 as hours_since_last
        from public.evidence_items
        where claim_type in ({claims_sql})
          and fetched_at > now() - interval '{days} days'
        group by claim_type
        order by claim_type;
    """)

    # Collector-level breakdown: group by source_type + domain extracted from source_url
    # Uses per-claim freshness windows same as above
    collector_rows = _sql(conn, f"""
        select
            claim_type,
            coalesce(
                nullif(source_type, '') || ':' ||
                    coalesce(
                        substring(source_url from '://([^/]+)'),
                        nullif(source_name, ''),
                        'unknown'
                    ),
                nullif(source_name, ''),
                'unknown'
            ) as collector,
            count(*) filter (
                where fetched_at > now() - (case claim_type {fresh_case}
                    else interval '{INGESTION_STALE_HOURS_DEFAULT} hours' end)
            ) as fresh_window
        from public.evidence_items
        where claim_type in ({claims_sql})
          and fetched_at > now() - interval '{days} days'
        group by claim_type, collector
        order by claim_type, collector;
    """)
    # Build lookup: claim_type → list of stalled collectors
    stalled_collectors: dict[str, list[str]] = {}
    for cr in collector_rows:
        if int(cr.get("fresh_window") or 0) == 0:
            ct = cr["claim_type"]
            stalled_collectors.setdefault(ct, []).append(cr["collector"])

    if not stale_rows:
        results.append(_result(
            "DATA", "evidence_health", "PASS",
            f"No critical evidence in last {days}d (empty cache)",
        ))
    else:
        for row in stale_rows:
            ct = row["claim_type"]
            total = int(row["total_window"])
            expired = int(row["expired_count"])
            fresh_win = int(row["fresh_window"])
            hours_since = float(row.get("hours_since_last") or 0)
            ratio = expired / total if total > 0 else 0
            pct = round(ratio * 100, 1)

            # Per-claim thresholds
            min_volume = INGESTION_MIN_7D.get(ct, INGESTION_MIN_7D_DEFAULT)
            stale_hours = INGESTION_STALE_HOURS.get(ct, INGESTION_STALE_HOURS_DEFAULT)
            window_label = f"fresh_{stale_hours}h"

            # Classify: STALLED vs LOW_VOLUME vs CACHE_STALE vs healthy
            is_stalled = (fresh_win == 0 and hours_since > stale_hours)
            is_low_volume = (fresh_win > 0 and total < min_volume)

            # Collector hint (only for stalled)
            stalled = stalled_collectors.get(ct, [])
            collector_hint = ""
            if stalled and is_stalled:
                collector_hint = f" Likely stalled: {', '.join(stalled[:3])}"

            if is_stalled and ratio >= 0.50:
                # Dead: no fresh evidence + high staleness → scraper down
                status = "FAIL" if ct == "price" else "WARN"
                label = "INGESTION STALLED"
                detail = (
                    f"[{label}] {ct}: {pct}% expired "
                    f"(total_{days}d={total}, {window_label}=0, "
                    f"last_fetch={int(hours_since)}h ago)"
                    f"{collector_hint}"
                    f" -> Check collector logs/cron"
                )
            elif is_low_volume:
                # Alive but underpowered
                status = "WARN"
                label = "LOW VOLUME"
                detail = (
                    f"[{label}] {ct}: total_{days}d={total} "
                    f"(min={min_volume}), {window_label}={fresh_win} "
                    f"-> collecting but below threshold for reliable scoring"
                )
            elif ratio >= STALE_FAIL_RATIO and ct == "price":
                status = "FAIL"
                label = "CACHE STALE"
                detail = (
                    f"[{label}] {ct}: {pct}% expired "
                    f"(total_{days}d={total}, {window_label}={fresh_win}) "
                    f"-> pipeline operating on junk prices"
                )
            elif ratio >= STALE_WARN_RATIO:
                status = "WARN"
                label = "CACHE STALE"
                detail = (
                    f"[{label}] {ct}: {pct}% expired "
                    f"(total_{days}d={total}, {window_label}={fresh_win}) "
                    f"-> run collectors more frequently or increase TTL"
                )
            else:
                status = "PASS"
                detail = (
                    f"{ct}: {pct}% expired "
                    f"(total_{days}d={total}, {window_label}={fresh_win})"
                )

            results.append(_result("DATA", f"evidence_{ct}", status, detail))

    return results


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report(results: list[dict]) -> str:
    """Format results as a sectioned, scannable report."""
    lines = [f"RayVault Doctor Report ({_dual_time()})"]

    # Group by section
    sections: dict[str, list[dict]] = {}
    for r in results:
        sections.setdefault(r["section"], []).append(r)

    # Summary line at top
    sec_summaries = []
    for sec_name in ["SECURITY", "FORENSICS", "DATA"]:
        checks = sections.get(sec_name, [])
        if not checks:
            continue
        fails = sum(1 for c in checks if c["status"] == "FAIL")
        warns = sum(1 for c in checks if c["status"] == "WARN")
        if fails:
            sec_summaries.append(f"FAIL {sec_name.lower()}")
        elif warns:
            sec_summaries.append(f"WARN {sec_name.lower()}")
        else:
            sec_summaries.append(f"PASS {sec_name.lower()}")

    if sec_summaries:
        lines.append(f"  SUMMARY: {' | '.join(sec_summaries)}")
    lines.append("")

    status_icon = {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN", "SKIP": "SKIP"}

    for section_name in ["SECURITY", "FORENSICS", "DATA"]:
        checks = sections.get(section_name, [])
        if not checks:
            continue
        lines.append(f"  {section_name}")
        for r in checks:
            icon = status_icon.get(r["status"], "????")
            detail_lines = r["detail"].split("\n")
            lines.append(f"    [{icon:>4s}] {r['check']}: {detail_lines[0]}")
            for extra in detail_lines[1:]:
                lines.append(f"           {extra}")
        lines.append("")

    # Counts
    pass_c = sum(1 for r in results if r["status"] == "PASS")
    fail_c = sum(1 for r in results if r["status"] == "FAIL")
    warn_c = sum(1 for r in results if r["status"] == "WARN")
    skip_c = sum(1 for r in results if r["status"] == "SKIP")
    total = len(results)

    lines.append(f"  {total} checks | {pass_c} passed | {fail_c} failed | {warn_c} warnings | {skip_c} skipped")

    # Next Actions (numbered, actionable)
    next_actions = _build_next_actions(results)
    if next_actions:
        lines.append("")
        lines.append("  Next Actions:")
        for i, action in enumerate(next_actions, 1):
            lines.append(f"    {i}. {action}")
    elif skip_c == total:
        lines.append("")
        lines.append("  Set DATABASE_URL and/or SUPABASE_URL + SUPABASE_ANON_KEY to run checks.")
    elif fail_c == 0 and warn_c == 0:
        lines.append("")
        lines.append("  All checks passed. Infrastructure is production-ready.")

    return "\n".join(lines)


def _build_next_actions(results: list[dict]) -> list[str]:
    """Generate prioritized, numbered action items from check results."""
    actions: list[str] = []

    # Security failures first (highest priority)
    sec_fails = [r for r in results if r["section"] == "SECURITY" and r["status"] == "FAIL"]
    if sec_fails:
        actions.append("URGENT: fix RLS — backend is writable from anon/authenticated")

    # Forensics failures
    forensic_fails = [r for r in results if r["section"] == "FORENSICS" and r["status"] == "FAIL"]
    if forensic_fails:
        actions.append("Run 008_forensic_hardening.sql in Supabase SQL Editor")

    # Audit trail missing
    audit_fail = [r for r in results if r["check"] == "audit_trail_populated" and r["status"] in ("FAIL", "WARN")]
    if audit_fail:
        actions.append("Check run_manager: run_evidence not being populated")

    # Ingestion stalled
    ingestion = [r for r in results if "INGESTION STALLED" in r.get("detail", "")]
    if ingestion:
        claims = [r["check"].replace("evidence_", "") for r in ingestion]
        actions.append(f"Check collector logs/cron for: {', '.join(claims)}")

    # Ghost runs
    ghost = [r for r in results if r["check"] == "ghost_runs" and r["status"] == "WARN"]
    if ghost:
        actions.append("Resolve stuck runs (approve/abort via Telegram or manual)")

    # Low volume
    low_vol = [r for r in results if "LOW VOLUME" in r.get("detail", "")]
    if low_vol:
        claims = [r["check"].replace("evidence_", "") for r in low_vol]
        actions.append(f"Low evidence volume for: {', '.join(claims)} — add sources or check niche coverage")

    # Cache stale
    stale = [r for r in results if "CACHE STALE" in r.get("detail", "")]
    if stale:
        actions.append("Run collectors more frequently or tune TTL for stale claims")

    # Supply low
    supply = [r for r in results if r["check"] == "supply_vs_demand" and r["status"] == "WARN"]
    if supply:
        actions.append("Ingestion capacity low — add collectors or reduce run frequency")

    return actions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="RayVault Doctor — Infrastructure Health Check")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quick", action="store_true",
                        help="Forensics + indexes only (no REST probes, no data health)")
    parser.add_argument("--security", action="store_true",
                        help="RLS lockdown probes only")
    parser.add_argument("--health", action="store_true",
                        help="Data health only (ghost runs, orphans, stale evidence)")
    parser.add_argument("--days", type=int, default=7,
                        help="Time window for health queries (default: 7)")
    args = parser.parse_args()

    load_env_file()

    # Determine which sections to run
    # If no flags → run all. If any flag → run only that section.
    run_all = not (args.quick or args.security or args.health)
    run_security = run_all or args.security
    run_forensics = run_all or args.quick
    run_data = run_all or args.health

    results: list[dict] = []

    # SECURITY (anon REST probes)
    if run_security:
        results.extend(check_security(quick=args.quick))

    # FORENSICS + DATA (admin DB)
    need_db = run_forensics or run_data
    if need_db:
        conn, err = _get_admin_db()
        if conn:
            try:
                if run_forensics:
                    results.extend(check_forensics(conn))
                if run_data:
                    results.extend(check_data_health(conn, days=args.days))
            finally:
                conn.close()
        else:
            if run_forensics:
                results.append(_result("FORENSICS", "db_connection", "SKIP", err or "No admin DB connection"))
            if run_data:
                results.append(_result("DATA", "db_connection", "SKIP", err or "No admin DB connection"))

    # Output
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_report(results))

    # Exit codes: 1 = FAIL, 2 = WARN only, 0 = clean
    has_fail = any(r["status"] == "FAIL" for r in results)
    has_warn = any(r["status"] == "WARN" for r in results)
    if has_fail:
        sys.exit(1)
    elif has_warn:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
