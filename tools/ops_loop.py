#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import random
import sys
import uuid

sys.path.insert(0, os.path.dirname(__file__))
from lib.common import load_json, now_iso, save_json

BASE_DIR = os.getenv("OPS_DIR", os.path.expanduser("~/.config/newproject/ops"))
os.makedirs(BASE_DIR, exist_ok=True)
POLICIES = os.path.join(BASE_DIR, "policies.json")
PROPOSALS = os.path.join(BASE_DIR, "proposals.json")
MISSIONS = os.path.join(BASE_DIR, "missions.json")
EVENTS = os.path.join(BASE_DIR, "events.jsonl")
REACTIONS = os.path.join(BASE_DIR, "reactions.json")


DEFAULT_STEPS = [
    "trend_scan",
    "research",
    "script",
    "assets",
    "seo",
    "edit",
    "review",
    "qa",
    "export",
    "upload",
]


def append_event(event_type, message, data=None):
    payload = {"ts": now_iso(), "type": event_type, "message": message}
    if data:
        payload["data"] = data
    with open(EVENTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def daily_count(event_type):
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    count = 0
    if not os.path.exists(EVENTS):
        return 0
    with open(EVENTS, "r", encoding="utf-8") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") != event_type:
                continue
            if ev.get("ts", "").startswith(today):
                count += 1
    return count


def gate_check(policies):
    if daily_count("video_published") >= policies.get("daily_video_cap", 1):
        return False, "daily_video_cap reached"
    if daily_count("short_published") >= policies.get("daily_shorts_cap", 3):
        return False, "daily_shorts_cap reached"
    return True, ""


def propose(title, category):
    policies = load_json(POLICIES, {})
    proposals = load_json(PROPOSALS, [])
    missions = load_json(MISSIONS, [])

    ok, reason = gate_check(policies)
    proposal_id = f"prop_{uuid.uuid4().hex[:8]}"
    proposal = {
        "id": proposal_id,
        "title": title,
        "category": category,
        "status": "pending",
        "created_at": now_iso(),
        "reason": None,
    }

    if not ok:
        proposal["status"] = "rejected"
        proposal["reason"] = reason
        proposals.append(proposal)
        save_json(PROPOSALS, proposals)
        append_event("proposal_rejected", reason, {"proposal_id": proposal_id})
        return proposal

    if policies.get("auto_approve", {}).get("enabled", True):
        proposal["status"] = "approved"
        proposals.append(proposal)
        mission_id = f"mission_{uuid.uuid4().hex[:8]}"
        mission = {
            "id": mission_id,
            "proposal_id": proposal_id,
            "title": title,
            "status": "queued",
            "created_at": now_iso(),
            "steps": [
                {
                    "id": f"step_{uuid.uuid4().hex[:6]}",
                    "kind": step,
                    "status": "queued",
                    "reserved_at": None,
                }
                for step in DEFAULT_STEPS
            ],
        }
        missions.append(mission)
        save_json(PROPOSALS, proposals)
        save_json(MISSIONS, missions)
        append_event("proposal_approved", "auto_approved", {"proposal_id": proposal_id, "mission_id": mission_id})
        return proposal

    proposals.append(proposal)
    save_json(PROPOSALS, proposals)
    append_event("proposal_pending", "manual_review_required", {"proposal_id": proposal_id})
    return proposal


def list_status():
    proposals = load_json(PROPOSALS, [])
    missions = load_json(MISSIONS, [])
    return {"proposals": proposals, "missions": missions}


def update_step(mission_id, step_id, status, error=None):
    missions = load_json(MISSIONS, [])
    for m in missions:
        if m["id"] != mission_id:
            continue
        for s in m["steps"]:
            if s["id"] != step_id:
                continue
            s["status"] = status
            if status == "running":
                s["reserved_at"] = now_iso()
            if status in ("succeeded", "failed"):
                s["reserved_at"] = None
            if error:
                s["error"] = error
        if all(step["status"] == "succeeded" for step in m["steps"]):
            m["status"] = "succeeded"
            append_event("mission_succeeded", m["title"], {"mission_id": m["id"]})
        elif any(step["status"] == "failed" for step in m["steps"]):
            m["status"] = "failed"
            append_event("mission_failed", m["title"], {"mission_id": m["id"]})
        else:
            m["status"] = "running"
    save_json(MISSIONS, missions)


def recover_stale():
    policies = load_json(POLICIES, {})
    stale_minutes = policies.get("stale_step_minutes", 30)
    missions = load_json(MISSIONS, [])
    threshold = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=stale_minutes)

    for m in missions:
        for s in m["steps"]:
            if s["status"] != "running" or not s.get("reserved_at"):
                continue
            try:
                reserved = dt.datetime.fromisoformat(s["reserved_at"].replace("Z", "+00:00"))
            except ValueError:
                continue
            if reserved < threshold:
                s["status"] = "failed"
                s["error"] = "stale step"
    save_json(MISSIONS, missions)
    append_event("recover_stale", f"checked stale steps ({stale_minutes}m)")


def main():
    p = argparse.ArgumentParser(description="Local closed-loop ops tool")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("propose")
    sp.add_argument("--title", required=True)
    sp.add_argument("--category", required=True)

    sub.add_parser("list")

    cp = sub.add_parser("claim-step")
    cp.add_argument("--mission-id", required=True)
    cp.add_argument("--step-id", required=True)

    dp = sub.add_parser("complete-step")
    dp.add_argument("--mission-id", required=True)
    dp.add_argument("--step-id", required=True)

    fp = sub.add_parser("fail-step")
    fp.add_argument("--mission-id", required=True)
    fp.add_argument("--step-id", required=True)
    fp.add_argument("--error", default="failed")

    sub.add_parser("recover-stale")

    args = p.parse_args()

    if args.cmd == "propose":
        proposal = propose(args.title, args.category)
        print(json.dumps(proposal, indent=2))
        return
    if args.cmd == "list":
        print(json.dumps(list_status(), indent=2))
        return
    if args.cmd == "claim-step":
        update_step(args.mission_id, args.step_id, "running")
        return
    if args.cmd == "complete-step":
        update_step(args.mission_id, args.step_id, "succeeded")
        return
    if args.cmd == "fail-step":
        update_step(args.mission_id, args.step_id, "failed", error=args.error)
        return
    if args.cmd == "recover-stale":
        recover_stale()
        return

    p.print_help()


if __name__ == "__main__":
    main()
