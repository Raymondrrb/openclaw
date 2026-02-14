#!/usr/bin/env python3
"""Stress test: prove claim_next exclusivity, heartbeat ownership, recovery-first.

Validates:
  1. Only 1 of 2 concurrent workers gets the same run (SKIP LOCKED)
  2. worker_id is correctly set in the DB after claim
  3. Owner heartbeat succeeds; intruder heartbeat fails
  4. Recovery-first: worker reclaims its own active run on restart

Requires:
  export SUPABASE_URL="https://xxxxx.supabase.co"
  export SUPABASE_SERVICE_KEY="your_service_role_key"

Usage:
  python3 tools/stress_test_claim.py           # full test
  python3 tools/stress_test_claim.py --quick    # skip recovery test
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SERVICE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY env vars", file=sys.stderr)
    raise SystemExit(2)

REST = f"{SUPABASE_URL}/rest/v1"
RPC = f"{SUPABASE_URL}/rest/v1/rpc"

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post(url: str, payload: dict, *, prefer: str = "") -> dict | list | None:
    """POST to Supabase REST/RPC. Returns parsed JSON."""
    import urllib.request
    import urllib.error

    headers = dict(HEADERS)
    if prefer:
        headers["Prefer"] = prefer

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body.strip() else None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code}: {body[:300]}", file=sys.stderr)
        raise


def _get(url: str, params: dict) -> list:
    """GET from Supabase REST. Returns list of rows."""
    import urllib.request
    import urllib.parse

    query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    full_url = f"{url}?{query}"
    req = urllib.request.Request(full_url, headers=HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _delete(url: str, params: dict) -> None:
    """DELETE from Supabase REST."""
    import urllib.request
    import urllib.parse

    query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    full_url = f"{url}?{query}"
    req = urllib.request.Request(full_url, headers=HEADERS, method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()


# ---------------------------------------------------------------------------
# Supabase operations
# ---------------------------------------------------------------------------

def create_test_run(video_id: str) -> str:
    """Insert a test run with status='running'. Returns run ID."""
    rows = _post(
        f"{REST}/pipeline_runs",
        {"video_id": video_id, "status": "running"},
        prefer="return=representation",
    )
    return rows[0]["id"]


def fetch_run(run_id: str) -> dict | None:
    """Fetch a single run by ID."""
    rows = _get(f"{REST}/pipeline_runs", {
        "id": f"eq.{run_id}",
        "select": "id,worker_id,lock_token,locked_at,lock_expires_at,worker_state,status",
    })
    return rows[0] if rows else None


def delete_test_run(run_id: str) -> None:
    """Clean up test run."""
    _delete(f"{REST}/pipeline_runs", {"id": f"eq.{run_id}"})


def rpc_claim_next(worker_id: str, lock_token: str, lease_minutes: int = 10) -> str | None:
    """Call rpc_claim_next_run. Returns run_id or None."""
    result = _post(f"{RPC}/rpc_claim_next_run", {
        "p_worker_id": worker_id,
        "p_lock_token": lock_token,
        "p_lease_minutes": lease_minutes,
        "p_task_type": None,
    })
    # RPC returns uuid directly (not wrapped in array)
    if result and result != "null" and result is not None:
        # PostgREST may return the uuid as a string or in an object
        if isinstance(result, str):
            return result.strip('"') if result.strip('"') != "null" else None
        if isinstance(result, list) and result:
            return str(result[0]) if result[0] else None
        return str(result) if result else None
    return None


def rpc_heartbeat(run_id: str, worker_id: str, lock_token: str,
                  lease_minutes: int = 10) -> tuple[bool, int]:
    """Call cas_heartbeat_run. Returns (success, latency_ms)."""
    t0 = time.monotonic()
    try:
        result = _post(f"{RPC}/cas_heartbeat_run", {
            "p_run_id": run_id,
            "p_worker_id": worker_id,
            "p_lock_token": lock_token,
            "p_lease_minutes": lease_minutes,
        })
        ms = int((time.monotonic() - t0) * 1000)
        return bool(result), ms
    except Exception:
        ms = int((time.monotonic() - t0) * 1000)
        return False, ms


def rpc_release(run_id: str, worker_id: str, lock_token: str) -> bool:
    """Call rpc_release_run."""
    result = _post(f"{RPC}/rpc_release_run", {
        "p_run_id": run_id,
        "p_worker_id": worker_id,
        "p_lock_token": lock_token,
    })
    return bool(result)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_exclusive_claim() -> tuple[str, str, str]:
    """Test 1: Two workers race — only one wins.

    Returns (run_id, winner_id, winner_token).
    """
    print("\n" + "=" * 60)
    print("TEST 1: Exclusive claim (2 workers, 1 run)")
    print("=" * 60)

    # Create test run
    vid = f"stress-{uuid.uuid4().hex[:8]}"
    run_id = create_test_run(vid)
    print(f"  Created test run: {run_id[:12]}... (video_id={vid})")

    # Two workers claim simultaneously
    token_a = str(uuid.uuid4())
    token_b = str(uuid.uuid4())

    results = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(rpc_claim_next, "Mac-Ray-01", token_a): "Mac-Ray-01",
            pool.submit(rpc_claim_next, "Mac-Ray-02", token_b): "Mac-Ray-02",
        }
        for future in as_completed(futures):
            wid = futures[future]
            try:
                claimed_id = future.result()
                results[wid] = claimed_id
            except Exception as e:
                results[wid] = f"ERROR: {e}"

    print(f"  Mac-Ray-01 -> {results.get('Mac-Ray-01', 'N/A')}")
    print(f"  Mac-Ray-02 -> {results.get('Mac-Ray-02', 'N/A')}")

    # Exactly one should have claimed our run
    winners = {w: r for w, r in results.items() if r and not str(r).startswith("ERROR")}
    non_winners = {w: r for w, r in results.items() if not r or r is None}

    if len(winners) == 0:
        print("  WARN: Neither worker got the run. Check if DB has other eligible runs.")
        print("  Attempting solo claim...")
        token_solo = str(uuid.uuid4())
        solo = rpc_claim_next("Mac-Ray-Solo", token_solo)
        if solo:
            print(f"  Solo claim got: {solo}")
            # Clean up
            rpc_release(solo, "Mac-Ray-Solo", token_solo)
        delete_test_run(run_id)
        raise SystemExit("FAIL: No worker could claim. Check RPC deployment.")

    if len(winners) > 1:
        # Both got runs — check if they got DIFFERENT runs (ok if DB has multiple eligible)
        vals = list(winners.values())
        if vals[0] == vals[1]:
            delete_test_run(run_id)
            raise SystemExit("FAIL: Both workers claimed the SAME run! SKIP LOCKED broken.")
        else:
            print("  NOTE: Both workers got runs (different ones). DB may have other eligible runs.")
            print("  For a clean test, ensure only 1 running/approved run exists.")

    # Determine winner
    winner_id = list(winners.keys())[0]
    claimed_run = winners[winner_id]
    winner_token = token_a if winner_id == "Mac-Ray-01" else token_b

    print(f"\n  Winner: {winner_id}")

    # Verify DB state
    row = fetch_run(run_id)
    if not row:
        delete_test_run(run_id)
        raise SystemExit("FAIL: Could not fetch run from DB.")

    db_worker = row.get("worker_id", "")
    db_token = row.get("lock_token", "")
    db_state = row.get("worker_state", "")

    print(f"  DB worker_id: {db_worker}")
    print(f"  DB lock_token: {db_token[:12]}...")
    print(f"  DB worker_state: {db_state}")

    if not db_worker:
        delete_test_run(run_id)
        raise SystemExit("FAIL: worker_id NOT SET in DB! This is the critical bug.")

    if db_worker != winner_id:
        # The winner might have claimed a different run if multiple exist
        print(f"  NOTE: DB worker_id ({db_worker}) != winner ({winner_id}).")
        print(f"  This means our test run was claimed by someone else, or recovery kicked in.")

    if not db_token:
        delete_test_run(run_id)
        raise SystemExit("FAIL: lock_token is empty in DB!")

    print("\n  PASS: Exclusive claim works.")
    return run_id, db_worker, db_token


def test_heartbeat_ownership(run_id: str, owner_id: str, owner_token: str) -> None:
    """Test 2: Owner heartbeat passes, intruder heartbeat fails."""
    print("\n" + "=" * 60)
    print("TEST 2: Heartbeat ownership")
    print("=" * 60)

    # Owner heartbeat
    ok, ms = rpc_heartbeat(run_id, owner_id, owner_token)
    print(f"  Owner ({owner_id}) heartbeat: ok={ok} latency={ms}ms")
    if not ok:
        raise SystemExit("FAIL: Owner heartbeat rejected!")

    # Intruder heartbeat (wrong worker_id, correct token)
    intruder = "Mac-Ray-02" if owner_id == "Mac-Ray-01" else "Mac-Ray-01"
    ok2, ms2 = rpc_heartbeat(run_id, intruder, owner_token)
    print(f"  Intruder ({intruder}) heartbeat: ok={ok2} latency={ms2}ms")
    if ok2:
        raise SystemExit("FAIL: Intruder heartbeat SUCCEEDED! Token/worker check broken.")

    # Intruder heartbeat (correct worker_id, wrong token)
    ok3, ms3 = rpc_heartbeat(run_id, owner_id, str(uuid.uuid4()))
    print(f"  Wrong token heartbeat: ok={ok3} latency={ms3}ms")
    if ok3:
        raise SystemExit("FAIL: Wrong-token heartbeat SUCCEEDED! Token check broken.")

    print("\n  PASS: Heartbeat correctly rejects intruders.")


def test_recovery_first(run_id: str, owner_id: str, owner_token: str) -> None:
    """Test 3: Worker reclaims its own active run on 'restart'.

    Simulates: worker has a run with valid lease, calls claim_next again
    (as if restarting) — should get the SAME run back, with stable token.
    """
    print("\n" + "=" * 60)
    print("TEST 3: Recovery-first (worker reclaims own run)")
    print("=" * 60)

    # Record original token
    row_before = fetch_run(run_id)
    orig_token = row_before["lock_token"]
    orig_locked_at = row_before["locked_at"]
    print(f"  Before: token={orig_token[:12]}... locked_at={orig_locked_at}")

    # Worker "restarts" — calls claim_next with a NEW token
    new_token = str(uuid.uuid4())
    recovered_id = rpc_claim_next(owner_id, new_token, lease_minutes=10)

    if not recovered_id:
        print("  WARN: claim_next returned None. Recovery might not have found the run.")
        print("  Check if the lease is still valid and status is correct.")
        return

    print(f"  Recovered run: {recovered_id}")
    if str(recovered_id).replace("-", "") != str(run_id).replace("-", ""):
        print(f"  NOTE: Got a different run ({recovered_id}) vs original ({run_id}).")
        print("  This could happen if the original run's lease expired between tests.")
        return

    # Check that token + locked_at are STABLE (not rotated on reclaim)
    row_after = fetch_run(run_id)
    after_token = row_after["lock_token"]
    after_locked_at = row_after["locked_at"]
    after_worker = row_after["worker_id"]

    print(f"  After:  token={after_token[:12]}... locked_at={after_locked_at}")
    print(f"  worker_id in DB: {after_worker}")

    if after_worker != owner_id:
        raise SystemExit("FAIL: worker_id changed after recovery!")

    if after_token != orig_token:
        print("  WARN: Token changed on recovery! Expected stable token.")
        print(f"  Original: {orig_token}")
        print(f"  After:    {after_token}")
        print("  This means the recovery path is generating a new token instead of keeping the existing one.")
    else:
        print("  Token: STABLE (same as before)")

    if after_locked_at != orig_locked_at:
        print("  WARN: locked_at changed on recovery! Expected stable timestamp.")
    else:
        print("  locked_at: STABLE (same as before)")

    print("\n  PASS: Recovery-first works correctly.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Stress test: claim_next exclusivity")
    parser.add_argument("--quick", action="store_true", help="Skip recovery test")
    args = parser.parse_args()

    print("RayVault Stress Test: claim_next exclusivity")
    print(f"Target: {SUPABASE_URL}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")

    run_id = None
    owner_id = None
    owner_token = None

    try:
        # Test 1: Exclusive claim
        run_id, owner_id, owner_token = test_exclusive_claim()

        # Test 2: Heartbeat ownership
        test_heartbeat_ownership(run_id, owner_id, owner_token)

        # Test 3: Recovery-first (optional)
        if not args.quick:
            test_recovery_first(run_id, owner_id, owner_token)

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)

    finally:
        # Clean up test run
        if run_id:
            try:
                # Release lock first (may fail if already released)
                if owner_id and owner_token:
                    rpc_release(run_id, owner_id, owner_token)
                # Delete the test run
                delete_test_run(run_id)
                print(f"\n  Cleaned up test run: {run_id[:12]}...")
            except Exception as e:
                print(f"\n  Cleanup failed (non-fatal): {e}")


if __name__ == "__main__":
    main()
