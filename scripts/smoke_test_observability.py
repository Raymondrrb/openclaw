#!/usr/bin/env python3
"""Smoke Test: Observability stack validation.

Controlled, destructive-but-reversible test that validates:
  1. run_events INSERT (CRITICAL severity)
  2. pipeline_runs panic state transition
  3. incidents_critical_open VIEW reflects the incident
  4. (optional) Telegram alert delivery

Usage:
    python3 scripts/smoke_test_observability.py              # dry: no Telegram
    python3 scripts/smoke_test_observability.py --telegram    # with alert
    python3 scripts/smoke_test_observability.py --run-id UUID # use existing run

Requires: SUPABASE_URL + SUPABASE_SERVICE_KEY in .env or env.

Exit codes:
    0 = all checks passed
    1 = partial pass (some checks failed but cleanup succeeded)
    2 = critical failure (check output)
    3 = setup error (missing env, connectivity)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.lib.common import load_env_file

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SMOKE_PREFIX = "smoke-test-"
SMOKE_WORKER_ID = "smoke-test-worker"
SMOKE_TIMEOUT_SEC = 10


# ---------------------------------------------------------------------------
# Supabase REST helpers (stdlib only — no requests/httpx dependency)
# ---------------------------------------------------------------------------

def _supabase_headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _supabase_request(
    url: str,
    service_key: str,
    *,
    method: str = "GET",
    data: dict | list | None = None,
) -> tuple[int, list | dict]:
    """Make a Supabase REST API request. Returns (status_code, json_body)."""
    headers = _supabase_headers(service_key)
    body = json.dumps(data).encode() if data else None

    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=SMOKE_TIMEOUT_SEC) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        try:
            return e.code, json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return e.code, {"error": raw}


def _supabase_rpc(
    base_url: str,
    service_key: str,
    fn_name: str,
    params: dict,
) -> tuple[int, any]:
    """Call a Supabase RPC function."""
    url = f"{base_url}/rest/v1/rpc/{fn_name}"
    return _supabase_request(url, service_key, method="POST", data=params)


# ---------------------------------------------------------------------------
# Test steps
# ---------------------------------------------------------------------------

class SmokeResult:
    """Collects pass/fail for each step."""

    def __init__(self):
        self.steps: list[tuple[str, bool, str]] = []
        self.run_id: str | None = None

    def record(self, name: str, passed: bool, detail: str = ""):
        status = "PASS" if passed else "FAIL"
        self.steps.append((name, passed, detail))
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

    @property
    def all_passed(self) -> bool:
        return all(ok for _, ok, _ in self.steps)

    @property
    def summary(self) -> str:
        total = len(self.steps)
        passed = sum(1 for _, ok, _ in self.steps if ok)
        return f"{passed}/{total} checks passed"


def step_create_test_run(
    base_url: str, key: str, result: SmokeResult,
) -> str | None:
    """Create a temporary pipeline_run for testing. Returns run_id or None."""
    url = f"{base_url}/rest/v1/pipeline_runs"
    data = {
        "status": "running",
        "worker_id": SMOKE_WORKER_ID,
        "worker_state": "active",
        "task_type": "smoke_test",
        "lock_token": f"{SMOKE_PREFIX}{uuid.uuid4().hex[:12]}",
    }

    status, body = _supabase_request(url, key, method="POST", data=data)

    if status in (200, 201) and isinstance(body, list) and body:
        run_id = body[0].get("id")
        result.record("create_test_run", True, f"run_id=...{run_id[-8:]}")
        return run_id

    result.record("create_test_run", False, f"status={status} body={body}")
    return None


def step_insert_critical_event(
    base_url: str, key: str, run_id: str, result: SmokeResult,
) -> bool:
    """Insert a CRITICAL severity event into run_events."""
    url = f"{base_url}/rest/v1/run_events"
    event_id = str(uuid.uuid4())
    data = {
        "run_id": run_id,
        "event_type": "smoke_test_critical",
        "severity": "CRITICAL",
        "reason_key": "smoke_test_alert",
        "source": "smoke_test",
        "action_id": f"smoke-{event_id[:8]}",
        "payload": json.dumps({
            "test": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": "Smoke test CRITICAL event — safe to ignore",
        }),
    }

    status, body = _supabase_request(url, key, method="POST", data=data)
    ok = status in (200, 201)
    result.record("insert_critical_event", ok, f"status={status}")
    return ok


def step_set_panic_state(
    base_url: str, key: str, run_id: str, result: SmokeResult,
) -> bool:
    """Set worker_state=panic on the test run."""
    url = (
        f"{base_url}/rest/v1/pipeline_runs"
        f"?id=eq.{run_id}"
    )
    data = {"worker_state": "panic"}

    status, body = _supabase_request(url, key, method="PATCH", data=data)
    ok = status in (200, 204)
    result.record("set_panic_state", ok, f"status={status}")
    return ok


def step_check_incidents_view(
    base_url: str, key: str, run_id: str, result: SmokeResult,
) -> bool:
    """Verify incidents_critical_open VIEW contains our test run."""
    # Small delay for view materialization
    time.sleep(1)

    url = (
        f"{base_url}/rest/v1/incidents_critical_open"
        f"?run_id=eq.{run_id}"
        f"&select=run_id,top_severity,worker_state,is_stale"
    )

    status, body = _supabase_request(url, key, method="GET")

    if status == 200 and isinstance(body, list) and len(body) > 0:
        row = body[0]
        sev = row.get("top_severity", "")
        ws = row.get("worker_state", "")
        detail = f"severity={sev} worker_state={ws}"

        # Verify it shows as CRITICAL and panic
        sev_ok = sev == "CRITICAL"
        ws_ok = ws == "panic"

        if sev_ok and ws_ok:
            result.record("incidents_view_contains_run", True, detail)
            return True
        else:
            result.record(
                "incidents_view_contains_run", False,
                f"unexpected: {detail} (expected CRITICAL+panic)",
            )
            return False

    if status == 200 and isinstance(body, list) and len(body) == 0:
        result.record(
            "incidents_view_contains_run", False,
            "run not found in incidents_critical_open (view may not be deployed)",
        )
        return False

    result.record("incidents_view_contains_run", False, f"status={status} body={body}")
    return False


def step_telegram_alert(
    bot_token: str, chat_id: str, run_id: str, result: SmokeResult,
) -> bool:
    """Send a test alert via Telegram."""
    if not bot_token or not chat_id:
        result.record("telegram_alert", False, "missing TELEGRAM_BOT_TOKEN or TELEGRAM_ADMIN_CHAT_ID")
        return False

    text = (
        f"SMOKE TEST\n"
        f"Run: ...{run_id[-8:]}\n"
        f"Time: {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}\n"
        f"Status: incidents_critical_open validated\n\n"
        f"This is a test alert — safe to ignore."
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"})

    try:
        with urlopen(req, timeout=SMOKE_TIMEOUT_SEC) as resp:
            ok = resp.status == 200
            result.record("telegram_alert", ok, f"status={resp.status}")
            return ok
    except (HTTPError, URLError) as e:
        result.record("telegram_alert", False, str(e))
        return False


def step_cleanup(
    base_url: str, key: str, run_id: str, result: SmokeResult,
) -> bool:
    """Delete the test run and its events. Cascade handles run_events."""
    url = f"{base_url}/rest/v1/pipeline_runs?id=eq.{run_id}"

    status, body = _supabase_request(url, key, method="DELETE")
    ok = status in (200, 204)
    result.record("cleanup", ok, f"status={status}")
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test for RayVault observability stack",
    )
    parser.add_argument(
        "--telegram", action="store_true",
        help="Send a test Telegram alert (requires TELEGRAM_* env vars)",
    )
    parser.add_argument(
        "--run-id", type=str, default="",
        help="Use an existing run_id instead of creating a new one",
    )
    parser.add_argument(
        "--no-cleanup", action="store_true",
        help="Skip cleanup (leave test data for manual inspection)",
    )
    args = parser.parse_args()

    # Load .env
    import os
    load_env_file()

    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", "")

    if not base_url or not service_key:
        print("[ERROR] Missing SUPABASE_URL or SUPABASE_SERVICE_KEY")
        return 3

    print("=== RayVault Smoke Test: Observability ===\n")

    result = SmokeResult()
    created_run = False

    # Step 1: Get or create test run
    if args.run_id:
        run_id = args.run_id
        result.record("use_existing_run", True, f"run_id=...{run_id[-8:]}")
    else:
        run_id = step_create_test_run(base_url, service_key, result)
        created_run = True
        if not run_id:
            print(f"\n{result.summary}")
            return 2

    result.run_id = run_id

    # Step 2: Insert CRITICAL event
    step_insert_critical_event(base_url, service_key, run_id, result)

    # Step 3: Set panic state
    step_set_panic_state(base_url, service_key, run_id, result)

    # Step 4: Check incidents view
    step_check_incidents_view(base_url, service_key, run_id, result)

    # Step 5: Optional Telegram
    if args.telegram:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")
        step_telegram_alert(bot_token, chat_id, run_id, result)

    # Step 6: Cleanup
    if not args.no_cleanup and created_run:
        step_cleanup(base_url, service_key, run_id, result)
    elif args.no_cleanup:
        print("  [SKIP] cleanup — --no-cleanup flag set")
    else:
        print("  [SKIP] cleanup — using existing run_id")

    # Summary
    print(f"\n{'=' * 40}")
    print(f"Result: {result.summary}")

    if result.all_passed:
        print("Observability stack is GO.")
        return 0
    else:
        print("Some checks failed — review output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
