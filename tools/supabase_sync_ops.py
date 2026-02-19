#!/usr/bin/env python3
"""
Sync local ops state files to Supabase (PostgREST).

Source files:
- <PROJECT_ROOT>/ops/policies.json
- <PROJECT_ROOT>/ops/proposals.json
- <PROJECT_ROOT>/ops/missions.json
- <PROJECT_ROOT>/ops/events.jsonl
"""

import argparse
import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Tuple

from lib.common import load_json, load_jsonl, now_iso


DEFAULT_OPS_DIR = os.getenv("OPS_DIR", os.path.expanduser("~/.config/newproject/ops"))


class SupabasePostgrest:
    def __init__(self, url: str, service_key: str, schema: str = "public"):
        self.base = url.rstrip("/") + "/rest/v1"
        self.schema = schema
        self.base_headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Profile": schema,
            "Content-Profile": schema,
        }

    def request(
        self,
        method: str,
        table: str,
        rows: List[Dict[str, Any]],
        on_conflict: str = "",
        return_representation: bool = False,
    ) -> Tuple[int, str]:
        if not rows:
            return 200, ""

        qs = {}
        if on_conflict:
            qs["on_conflict"] = on_conflict

        endpoint = f"{self.base}/{table}"
        if qs:
            endpoint += "?" + urllib.parse.urlencode(qs)

        headers = dict(self.base_headers)
        if return_representation:
            headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        else:
            headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

        data = json.dumps(rows).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return resp.status, body
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code} {table}: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error calling Supabase: {e}") from e


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sync local ops files to Supabase")
    p.add_argument("--ops-dir", default=DEFAULT_OPS_DIR, help="Path to ops directory")
    p.add_argument("--events-limit", type=int, default=0, help="Only sync last N events (0 = all)")
    p.add_argument("--batch-size", type=int, default=500, help="Upsert rows per request")
    p.add_argument("--max-retries", type=int, default=3, help="Retries for 429/5xx responses")
    p.add_argument("--dry-run", action="store_true", help="Print row counts only")
    return p.parse_args()


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def decode_jwt_payload(token: str) -> Dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload_b64 = parts[1]
    payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
    try:
        payload_raw = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        payload = json.loads(payload_raw.decode("utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


def validate_supabase_service_key(service_key: str) -> None:
    if not service_key or not str(service_key).strip():
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is empty or None.")
    # Block obvious incorrect key type for backend sync.
    if service_key.startswith("sb_publishable_"):
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY appears to be a publishable key. "
            "Use a secret key (sb_secret_...) or legacy service_role JWT key."
        )
    # Fail-closed for JWT-style keys: missing/undefined role must not pass.
    # (Supabase "sb_secret_*" keys are not JWTs and won't be parsed here.)
    if service_key.count(".") == 2:
        payload = decode_jwt_payload(service_key)
        role = str(payload.get("role", "")).strip().lower()
        if role != "service_role":
            raise RuntimeError(
                "SUPABASE_SERVICE_ROLE_KEY looks like a JWT, but role is missing or not 'service_role'. "
                "Use a backend elevated key (service_role JWT) or a non-JWT sb_secret_* key."
            )


def build_policy_rows(policies: Dict[str, Any]) -> List[Dict[str, Any]]:
    ts = now_iso()
    rows = []
    for key, value in policies.items():
        rows.append({"key": key, "value": value, "updated_at": ts})
    return rows


def build_proposal_rows(proposals: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for p in proposals:
        proposal_id = p.get("id")
        title = p.get("title")
        if not proposal_id or not title:
            continue
        rows.append(
            {
                "id": proposal_id,
                "title": title,
                "category": p.get("category"),
                "status": p.get("status", "pending"),
                "reason": p.get("reason"),
                "created_at": p.get("created_at") or now_iso(),
            }
        )
    return rows


def build_mission_rows(missions: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for m in missions:
        mission_id = m.get("id")
        title = m.get("title")
        if not mission_id or not title:
            continue
        rows.append(
            {
                "id": mission_id,
                "proposal_id": m.get("proposal_id"),
                "title": title,
                "status": m.get("status", "queued"),
                "created_at": m.get("created_at") or now_iso(),
            }
        )
    return rows


def build_step_rows(missions: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for m in missions:
        mission_id = m.get("id")
        if not mission_id:
            continue
        for s in m.get("steps", []):
            step_id = s.get("id")
            kind = s.get("kind")
            if not step_id or not kind:
                continue
            rows.append(
                {
                    "id": step_id,
                    "mission_id": mission_id,
                    "kind": kind,
                    "status": s.get("status", "queued"),
                    "reserved_at": s.get("reserved_at"),
                    "error": s.get("error"),
                }
            )
    return rows


def build_event_rows(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for ev in events:
        canonical = json.dumps(ev, sort_keys=True, ensure_ascii=False)
        event_hash = hashlib.sha1(canonical.encode("utf-8")).hexdigest()
        rows.append(
            {
                "event_hash": event_hash,
                "ts": ev.get("ts") or now_iso(),
                "type": ev.get("type", "event"),
                "message": ev.get("message", ""),
                "data": ev.get("data"),
            }
        )
    return rows


def chunk_rows(rows: List[Dict[str, Any]], batch_size: int) -> Iterable[List[Dict[str, Any]]]:
    if batch_size <= 0:
        yield rows
        return
    for i in range(0, len(rows), batch_size):
        yield rows[i : i + batch_size]


def upsert_with_retry(
    client: SupabasePostgrest,
    table: str,
    rows: List[Dict[str, Any]],
    *,
    on_conflict: str,
    batch_size: int,
    max_retries: int,
) -> None:
    for batch in chunk_rows(rows, batch_size):
        attempt = 0
        while True:
            try:
                client.request("POST", table, batch, on_conflict=on_conflict)
                break
            except RuntimeError as e:
                msg = str(e)
                transient = ("HTTP 429" in msg) or ("HTTP 5" in msg)
                if not transient or attempt >= max_retries:
                    raise
                sleep_s = min(8.0, 1.0 * (2**attempt))
                time.sleep(sleep_s)
                attempt += 1


def main() -> None:
    args = parse_args()
    ops_dir = args.ops_dir

    policies = load_json(os.path.join(ops_dir, "policies.json"), {})
    proposals = load_json(os.path.join(ops_dir, "proposals.json"), [])
    missions = load_json(os.path.join(ops_dir, "missions.json"), [])
    events = load_jsonl(os.path.join(ops_dir, "events.jsonl"), limit=args.events_limit)

    policy_rows = build_policy_rows(policies)
    proposal_rows = build_proposal_rows(proposals)
    mission_rows = build_mission_rows(missions)
    step_rows = build_step_rows(missions)
    event_rows = build_event_rows(events)

    summary = {
        "opsDir": ops_dir,
        "counts": {
            "policies": len(policy_rows),
            "proposals": len(proposal_rows),
            "missions": len(mission_rows),
            "steps": len(step_rows),
            "events": len(event_rows),
        },
        "dryRun": args.dry_run,
    }

    if args.dry_run:
        print(json.dumps(summary, indent=2))
        return

    supabase_url = require_env("SUPABASE_URL")
    service_key = require_env("SUPABASE_SERVICE_ROLE_KEY")
    validate_supabase_service_key(service_key)
    schema = os.getenv("SUPABASE_SCHEMA", "public").strip() or "public"

    client = SupabasePostgrest(supabase_url, service_key, schema=schema)

    upsert_with_retry(
        client,
        "ops_policy",
        policy_rows,
        on_conflict="key",
        batch_size=args.batch_size,
        max_retries=args.max_retries,
    )
    upsert_with_retry(
        client,
        "ops_mission_proposals",
        proposal_rows,
        on_conflict="id",
        batch_size=args.batch_size,
        max_retries=args.max_retries,
    )
    upsert_with_retry(
        client,
        "ops_missions",
        mission_rows,
        on_conflict="id",
        batch_size=args.batch_size,
        max_retries=args.max_retries,
    )
    upsert_with_retry(
        client,
        "ops_mission_steps",
        step_rows,
        on_conflict="id",
        batch_size=args.batch_size,
        max_retries=args.max_retries,
    )
    upsert_with_retry(
        client,
        "ops_agent_events",
        event_rows,
        on_conflict="event_hash",
        batch_size=args.batch_size,
        max_retries=args.max_retries,
    )

    summary["syncedAt"] = now_iso()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
