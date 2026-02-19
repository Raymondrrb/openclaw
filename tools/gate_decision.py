#!/usr/bin/env python3
"""
Approve/reject quality gates and trigger GO actions from the terminal.

Replaces the n8n webhook for gate decisions. Use this directly from
the terminal or in response to the daily GO/NO-GO Telegram message.

Usage:
  # Approve Gate 1
  python3 tools/gate_decision.py --run-slug portable_monitors_2026-02-09 --gate gate1 --decision approve

  # Reject Gate 2 with notes
  python3 tools/gate_decision.py --run-slug portable_monitors_2026-02-09 --gate gate2 --decision reject --notes "Thumbnail needs redo"

  # Trigger render after gate2 approval
  python3 tools/gate_decision.py --run-slug portable_monitors_2026-02-09 --action start_render

  # Mark as published
  python3 tools/gate_decision.py --run-slug portable_monitors_2026-02-09 --action mark_published

  # Reset a failed run
  python3 tools/gate_decision.py --run-slug portable_monitors_2026-02-09 --action reset_to_gate2

Required env vars:
  CONTROL_PLANE_URL    - e.g. https://new-project-control-plane.vercel.app
  OPS_GATE_SECRET      - Bearer token for /api/ops/gate
  OPS_GO_SECRET        - Bearer token for /api/ops/go
  TELEGRAM_CHAT_ID     - (optional) send confirmation to Telegram
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.control_plane import api_post, send_telegram


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Quality gate decision & GO actions (replaces n8n).")
    p.add_argument("--run-slug", required=True, help="Pipeline run slug")
    p.add_argument("--gate", choices=["gate1", "gate2"], help="Gate to approve/reject")
    p.add_argument("--decision", choices=["approve", "reject"], help="Approve or reject the gate")
    p.add_argument("--action", choices=["start_render", "start_upload", "mark_published", "mark_failed", "reset_to_gate2"],
                    help="GO action (alternative to --gate/--decision)")
    p.add_argument("--reviewer", default="Ray", help="Reviewer name (default: Ray)")
    p.add_argument("--notes", default="", help="Optional notes")
    p.add_argument("--auto-go", action="store_true", default=True,
                    help="Automatically trigger start_render when gate2 is approved (default: true)")
    p.add_argument("--no-auto-go", dest="auto_go", action="store_false",
                    help="Do NOT auto-trigger start_render on gate2 approve")
    p.add_argument("--notify", action="store_true", default=True,
                    help="Send Telegram confirmation (default: true)")
    p.add_argument("--no-notify", dest="notify", action="store_false")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if not args.gate and not args.action:
        print("ERROR: specify either --gate + --decision or --action", file=sys.stderr)
        return 2

    results = []

    # Gate decision
    if args.gate and args.decision:
        body = {
            "run_slug": args.run_slug,
            "gate": args.gate,
            "decision": args.decision,
            "reviewer": args.reviewer,
            "notes": args.notes or f"{args.decision} from CLI",
        }
        try:
            resp = api_post("/api/ops/gate", "OPS_GATE_SECRET", body)
            results.append(("gate", resp))
            print(f"Gate {args.gate} {args.decision}: OK")
            print(json.dumps(resp, indent=2))
        except Exception as e:
            print(f"ERROR (gate): {e}", file=sys.stderr)
            return 1

        # Auto-GO on gate2 approve
        if args.gate == "gate2" and args.decision == "approve" and args.auto_go:
            go_body = {
                "run_slug": args.run_slug,
                "action": "start_render",
                "requested_by": args.reviewer,
                "notes": "Auto-GO after gate2 approve",
            }
            try:
                go_resp = api_post("/api/ops/go", "OPS_GO_SECRET", go_body)
                results.append(("go", go_resp))
                print(f"\nAuto start_render: OK")
                print(json.dumps(go_resp, indent=2))
            except Exception as e:
                print(f"WARNING (auto-go): {e}", file=sys.stderr)

    # Direct GO action
    if args.action:
        go_body = {
            "run_slug": args.run_slug,
            "action": args.action,
            "requested_by": args.reviewer,
            "notes": args.notes or f"{args.action} from CLI",
        }
        try:
            resp = api_post("/api/ops/go", "OPS_GO_SECRET", go_body)
            results.append(("go", resp))
            print(f"Action {args.action}: OK")
            print(json.dumps(resp, indent=2))
        except Exception as e:
            print(f"ERROR (go): {e}", file=sys.stderr)
            return 1

    # Telegram notification
    if args.notify and results:
        parts = [f"Gate decision - {args.run_slug}"]
        for kind, resp in results:
            if kind == "gate":
                parts.append(f"  {args.gate} {args.decision} by {args.reviewer}")
            elif kind == "go":
                action = resp.get("action") or args.action or "?"
                parts.append(f"  GO: {action}")
        if args.notes:
            parts.append(f"  Notas: {args.notes}")
        send_telegram("\n".join(parts), message_kind="gate")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
