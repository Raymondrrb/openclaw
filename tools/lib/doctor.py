"""RayVault Doctor — health check + spool replay CLI.

Three modes:
  --replay-spool : push pending spool events to Supabase
  --health       : check ghost runs, stale gates, heartbeat latency
  --all          : both (default morning routine)

Stdlib + urllib only — no requests dependency.

Usage:
    python3 -m tools.lib.doctor --health
    python3 -m tools.lib.doctor --replay-spool
    python3 -m tools.lib.doctor --all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.lib.config import (
    load_worker_config,
    format_dual_time,
    WorkerConfig,
    SecretsConfig,
    HealthThresholds,
)


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only)
# ---------------------------------------------------------------------------

def _make_headers(service_key: str) -> Dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }


def _http_get(url: str, headers: Dict[str, str], timeout: int = 15) -> Tuple[int, Any]:
    """GET via urllib. Returns (status, parsed_json)."""
    import urllib.request
    import urllib.error

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body.strip() else []
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body
    except Exception as e:
        return 0, str(e)


def _http_post(url: str, data: dict, headers: Dict[str, str],
               timeout: int = 15) -> Tuple[int, str]:
    """POST via urllib. Returns (status, body)."""
    import urllib.request
    import urllib.error

    body_bytes = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, str(e)


# ---------------------------------------------------------------------------
# Spool replay
# ---------------------------------------------------------------------------

def replay_spool(
    spool_dir: str,
    supabase_url: str,
    service_key: str,
    timeout: int = 15,
    max_retries: int = 3,
) -> Tuple[int, int, int]:
    """Replay spool files: local -> Supabase run_events.

    Retry logic per file:
    - Each file tracks a retry_count inside the JSON.
    - On HTTP failure, retry_count is incremented and file is rewritten.
    - After max_retries failures, file is moved to spool/quarantine/.
    - Corrupted/invalid files are moved to spool/bad/ immediately.

    Returns (synced, failed, remaining).
    """
    spool = Path(spool_dir)
    if not spool.exists():
        return 0, 0, 0

    bad_dir = spool / "bad"
    quarantine_dir = spool / "quarantine"
    headers = _make_headers(service_key)
    ev_url = f"{supabase_url}/rest/v1/run_events"

    files = sorted(f for f in spool.iterdir() if f.is_file() and f.suffix == ".json")
    synced = 0
    failed = 0

    for f in files:
        # Parse
        try:
            with open(f, "r", encoding="utf-8") as fh:
                record = json.load(fh)
        except (json.JSONDecodeError, OSError):
            bad_dir.mkdir(parents=True, exist_ok=True)
            try:
                f.rename(bad_dir / f.name)
            except OSError:
                pass
            failed += 1
            continue

        run_id = record.get("run_id")
        if not run_id:
            bad_dir.mkdir(parents=True, exist_ok=True)
            try:
                f.rename(bad_dir / f.name)
            except OSError:
                pass
            failed += 1
            continue

        # Send to Supabase with SRE columns
        event_id = record.get("event_id", record.get("action_id", ""))
        event_data = {
            "run_id": run_id,
            "action_id": event_id,
            "event_id": event_id,
            "event_type": record.get("event_type", "spool_replay"),
            "severity": record.get("severity"),
            "reason_key": record.get("reason_key"),
            "source": record.get("source", "spool_replay"),
            "occurred_at": record.get("timestamp"),
            "payload": record,
        }

        status, _ = _http_post(ev_url, event_data, headers, timeout=timeout)
        # 409 = unique violation (event_id already exists) → treat as success
        if status < 300 or status == 409:
            try:
                f.unlink()
            except OSError:
                pass
            synced += 1
        else:
            # Increment retry count
            retries = record.get("_replay_retries", 0) + 1
            if retries >= max_retries:
                # Quarantine — too many failures
                quarantine_dir.mkdir(parents=True, exist_ok=True)
                try:
                    f.rename(quarantine_dir / f.name)
                except OSError:
                    pass
            else:
                # Rewrite with incremented retry count
                record["_replay_retries"] = retries
                try:
                    with open(f, "w", encoding="utf-8") as fh:
                        json.dump(record, fh, ensure_ascii=False, indent=2)
                except OSError:
                    pass
            failed += 1

    remaining = len([x for x in spool.iterdir()
                     if x.is_file() and x.suffix == ".json"])
    return synced, failed, remaining


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def health_check(
    supabase_url: str,
    service_key: str,
    thresholds: HealthThresholds,
    timeout: int = 15,
) -> Dict[str, Any]:
    """Run health checks against Supabase. Returns structured results."""
    import urllib.parse

    headers = _make_headers(service_key)
    now = datetime.now(timezone.utc)

    results: Dict[str, Any] = {
        "ghost_waiting": [],
        "stale_gate": [],
        "stale_workers": [],
        "latency_warn": [],
        "latency_crit": [],
        "active_runs": [],
        "counts": {},
    }

    # 1) Waiting approval runs
    select = "id,updated_at,worker_state,worker_id,last_heartbeat_at,last_heartbeat_latency_ms"
    url = (
        f"{supabase_url}/rest/v1/pipeline_runs"
        f"?select={select}"
        f"&status=eq.waiting_approval"
    )
    status, data = _http_get(url, headers, timeout=timeout)
    waiting = data if isinstance(data, list) else []

    ghost_cutoff = now - timedelta(hours=thresholds.ghost_run_hours)
    stale_cutoff = now - timedelta(hours=thresholds.stale_gate_hours)

    for r in waiting:
        try:
            updated = datetime.fromisoformat(
                r.get("updated_at", "").replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            continue

        if updated < ghost_cutoff:
            results["ghost_waiting"].append(r)
        if updated < stale_cutoff:
            results["stale_gate"].append(r)

    # 2) Active runs — check heartbeat latency
    select2 = "id,worker_state,worker_id,last_heartbeat_at,last_heartbeat_latency_ms"
    url2 = (
        f"{supabase_url}/rest/v1/pipeline_runs"
        f"?select={select2}"
        f"&or=(worker_state.eq.active,worker_state.eq.waiting)"
    )
    status2, data2 = _http_get(url2, headers, timeout=timeout)
    active = data2 if isinstance(data2, list) else []
    results["active_runs"] = active

    # Stale worker: active/waiting but no heartbeat for > stale_worker_minutes
    stale_cutoff_worker = now - timedelta(minutes=thresholds.stale_worker_minutes)

    for r in active:
        # Latency check
        lat = r.get("last_heartbeat_latency_ms")
        if lat is not None:
            if lat >= thresholds.heartbeat_latency_crit_ms:
                results["latency_crit"].append(r)
            elif lat >= thresholds.heartbeat_latency_warn_ms:
                results["latency_warn"].append(r)

        # Stale worker check: no heartbeat in too long
        hb_at = r.get("last_heartbeat_at")
        if hb_at:
            try:
                hb_time = datetime.fromisoformat(
                    hb_at.replace("Z", "+00:00")
                )
                if hb_time < stale_cutoff_worker:
                    age_min = int((now - hb_time).total_seconds() / 60)
                    r["_hb_age_min"] = age_min
                    results["stale_workers"].append(r)
            except (ValueError, TypeError):
                pass

    results["counts"] = {
        "waiting_total": len(waiting),
        "ghost": len(results["ghost_waiting"]),
        "stale_gate": len(results["stale_gate"]),
        "stale_workers": len(results["stale_workers"]),
        "active": len(active),
        "lat_warn": len(results["latency_warn"]),
        "lat_crit": len(results["latency_crit"]),
    }

    return results


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(
    results: Dict[str, Any],
    thresholds: HealthThresholds,
    spool_stats: Tuple[int, int, int] | None = None,
) -> None:
    """Print a human-readable health report."""
    now = datetime.now(timezone.utc)
    hr = "-" * 50

    print(f"\nRayVault Doctor — {format_dual_time(now)}")
    print(hr)

    if spool_stats:
        synced, failed, remaining = spool_stats
        label = "PASS" if remaining == 0 else "WARN"
        print(f"[SPOOL] {label}: synced={synced} failed={failed} remaining={remaining}")

    c = results.get("counts", {})
    health_ok = (
        c.get("ghost", 0) == 0
        and c.get("lat_crit", 0) == 0
        and c.get("stale_workers", 0) == 0
    )

    print(
        f"[HEALTH] {'PASS' if health_ok else 'FAIL'}"
        f" | waiting={c.get('waiting_total', 0)}"
        f" ghost={c.get('ghost', 0)}"
        f" stale_gate={c.get('stale_gate', 0)}"
        f" stale_workers={c.get('stale_workers', 0)}"
        f" active={c.get('active', 0)}"
        f" lat_warn={c.get('lat_warn', 0)}"
        f" lat_crit={c.get('lat_crit', 0)}"
    )

    # Details — stale workers first (most critical)
    if c.get("stale_workers", 0) > 0:
        print(f"\n[CRITICAL] Stale workers (no heartbeat > {thresholds.stale_worker_minutes}min):")
        for r in results["stale_workers"][:10]:
            print(
                f"  ...{r['id'][-8:]} worker={r.get('worker_id')}"
                f" hb_age={r.get('_hb_age_min', '?')}min"
                f" state={r.get('worker_state')}"
            )
        print("  Suggested: force_unlock if worker is dead, or restart worker.")

    if c.get("lat_crit", 0) > 0:
        print(f"\n[CRITICAL] Heartbeat latency >= {thresholds.heartbeat_latency_crit_ms}ms:")
        for r in results["latency_crit"][:10]:
            print(
                f"  ...{r['id'][-8:]} worker={r.get('worker_id')}"
                f" lat={r.get('last_heartbeat_latency_ms')}ms"
            )

    if c.get("lat_warn", 0) > 0:
        print(f"\n[WARN] Heartbeat latency >= {thresholds.heartbeat_latency_warn_ms}ms:")
        for r in results["latency_warn"][:10]:
            print(
                f"  ...{r['id'][-8:]} worker={r.get('worker_id')}"
                f" lat={r.get('last_heartbeat_latency_ms')}ms"
            )

    if c.get("ghost", 0) > 0:
        print(f"\n[WARN] Ghost runs (waiting_approval > {thresholds.ghost_run_hours}h):")
        for r in results["ghost_waiting"][:10]:
            print(f"  ...{r['id'][-8:]} worker={r.get('worker_id')} updated={r.get('updated_at')}")

    if c.get("stale_gate", 0) > 0:
        print(f"\n[STALE_GATE] waiting_approval > {thresholds.stale_gate_hours}h:")
        for r in results["stale_gate"][:10]:
            print(f"  ...{r['id'][-8:]} updated={r.get('updated_at')}")

    # Recommended actions
    actions = []
    if c.get("stale_workers", 0) > 0:
        actions.append("Stale workers detected: force_unlock dead runs or restart worker.")
    if c.get("lat_crit", 0) > 0:
        actions.append("Check Mac network (Wi-Fi/ISP) and Supabase status.")
    if c.get("ghost", 0) > 0:
        actions.append("Open dashboard: approve/abort/refetch ghost runs.")
    if c.get("stale_gate", 0) > 0:
        actions.append("Stale gates: trigger refetch — old evidence may be unsafe.")
    if spool_stats and spool_stats[2] > 0:
        actions.append("Spool has pending events: check service key / connectivity.")

    if actions:
        print(f"\n{hr}")
        print("NEXT ACTIONS:")
        for i, a in enumerate(actions, 1):
            print(f"  {i}. {a}")

    print()


# ---------------------------------------------------------------------------
# RPC contract check
# ---------------------------------------------------------------------------

# RPCs that must be callable by service_role
_REQUIRED_RPCS = (
    "rpc_claim_next_run",
    "cas_heartbeat_run",
    "rpc_release_run",
    "rpc_force_unlock_run",
)


def check_rpc_contract(
    supabase_url: str,
    service_key: str,
    timeout: int = 15,
) -> Tuple[List[str], List[str]]:
    """Verify all required RPCs are callable.

    Makes a harmless POST to each RPC endpoint with minimal params.
    Expected: 200 (returns result) or 400 (bad params but function exists).
    Failure: 404 (function missing) or 403 (permission denied).

    Returns (passed, failed) lists of RPC names.
    """
    headers = _make_headers(service_key)
    passed = []
    failed = []

    # Minimal payloads that exercise the function signature without side effects
    rpc_payloads = {
        "rpc_claim_next_run": {
            "p_worker_id": "__contract_check__",
            "p_lock_token": "00000000-0000-0000-0000-000000000000",
            "p_lease_minutes": 1,
            "p_task_type": None,
        },
        "cas_heartbeat_run": {
            "p_run_id": "00000000-0000-0000-0000-000000000000",
            "p_worker_id": "__contract_check__",
            "p_lock_token": "00000000-0000-0000-0000-000000000000",
            "p_lease_minutes": 1,
        },
        "rpc_release_run": {
            "p_run_id": "00000000-0000-0000-0000-000000000000",
            "p_worker_id": "__contract_check__",
            "p_lock_token": "00000000-0000-0000-0000-000000000000",
        },
        "rpc_force_unlock_run": {
            "p_run_id": "00000000-0000-0000-0000-000000000000",
            "p_operator_id": "__contract_check__",
            "p_reason": "contract_check",
            "p_force": False,
        },
    }

    for rpc_name in _REQUIRED_RPCS:
        url = f"{supabase_url}/rest/v1/rpc/{rpc_name}"
        payload = rpc_payloads.get(rpc_name, {})
        status, body = _http_post(url, payload, headers, timeout=timeout)

        # 200 = function exists and ran (may return null/false — that's fine)
        # 400 = function exists but params invalid (still means it's deployed)
        # 404 = function not found
        # 403 = permission denied (REVOKE/GRANT issue)
        if status in (200, 204):
            passed.append(rpc_name)
        elif status == 400:
            # Function exists but rejected params — contract OK
            passed.append(rpc_name)
        else:
            failed.append(rpc_name)

    return passed, failed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="rayvault-doctor",
        description="RayVault Doctor — health check + spool replay",
    )
    parser.add_argument("--replay-spool", action="store_true",
                        help="Replay pending spool events to Supabase")
    parser.add_argument("--health", action="store_true",
                        help="Run health checks (ghost runs, latency, stale gates)")
    parser.add_argument("--check-contract", action="store_true",
                        help="Verify all required RPCs are deployed and callable")
    parser.add_argument("--all", action="store_true",
                        help="Run --replay-spool + --health + --check-contract")
    args = parser.parse_args()

    if not (args.replay_spool or args.health or args.check_contract or args.all):
        parser.print_help()
        return 1

    cfg, secrets = load_worker_config()

    if not secrets.supabase_url or not secrets.supabase_service_key:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY", file=sys.stderr)
        return 2

    do_spool = args.replay_spool or args.all
    do_health = args.health or args.all
    do_contract = args.check_contract or args.all

    spool_stats = None
    if do_spool:
        spool_stats = replay_spool(
            cfg.spool_dir,
            secrets.supabase_url,
            secrets.supabase_service_key,
            timeout=cfg.rpc_timeout_sec,
        )

    # Contract check
    contract_failed = []
    if do_contract:
        passed, failed = check_rpc_contract(
            secrets.supabase_url,
            secrets.supabase_service_key,
            timeout=cfg.rpc_timeout_sec,
        )
        contract_failed = failed
        for name in passed:
            print(f"[CONTRACT] PASS: {name}")
        for name in failed:
            print(f"[CONTRACT] FAIL: {name}")
        if not failed:
            print(f"[CONTRACT] All {len(passed)} RPCs callable.")

    results: Dict[str, Any] = {"counts": {}}
    if do_health:
        results = health_check(
            secrets.supabase_url,
            secrets.supabase_service_key,
            cfg.thresholds,
            timeout=cfg.rpc_timeout_sec,
        )

    if do_health or spool_stats:
        print_report(results, cfg.thresholds, spool_stats=spool_stats)

    # Exit code: 2=CRITICAL, 1=WARN, 0=ok (automatable via cron)
    c = results.get("counts", {})
    has_critical = (
        c.get("stale_workers", 0) > 0
        or c.get("lat_crit", 0) > 0
        or len(contract_failed) > 0
    )
    has_warn = (
        c.get("ghost", 0) > 0
        or c.get("stale_gate", 0) > 0
        or c.get("lat_warn", 0) > 0
    )
    if has_critical:
        return 2
    if has_warn:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
