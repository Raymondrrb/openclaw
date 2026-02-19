#!/usr/bin/env python3
"""
Failure alert poller.

Replaces n8n Workflow 2: polls /api/ops/runs?status=failed every 10 minutes
and sends a Telegram alert if any failed runs exist.

Uses a local state file to avoid sending duplicate alerts for the same run.

Required env vars:
  CONTROL_PLANE_URL    - e.g. https://new-project-control-plane.vercel.app
  OPS_READ_SECRET      - Bearer token for /api/ops/runs
  TELEGRAM_CHAT_ID     - Telegram chat to send to
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from lib.common import now_iso, project_root
from lib.control_plane import api_get, send_telegram

ALERTED_FILE = project_root() / "tmp" / "failure_alert_seen.json"


def load_alerted() -> set:
    if not ALERTED_FILE.exists():
        return set()
    try:
        data = json.loads(ALERTED_FILE.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except (json.JSONDecodeError, OSError):
        return set()


def save_alerted(slugs: set) -> None:
    ALERTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    _tmp = ALERTED_FILE.with_suffix(".tmp")
    _payload = json.dumps(sorted(slugs)).encode("utf-8")
    _fd = os.open(str(_tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(_fd, _payload)
        os.fsync(_fd)
    finally:
        os.close(_fd)
    os.replace(str(_tmp), str(ALERTED_FILE))


def main() -> int:
    try:
        data = api_get("/api/ops/runs", "OPS_READ_SECRET", params={"limit": "10", "status": "failed"})
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    rows = data.get("rows", [])
    if not rows:
        print("No failed runs.")
        return 0

    alerted = load_alerted()
    new_failures = [r for r in rows if r.get("run_slug") not in alerted]

    if not new_failures:
        print(f"{len(rows)} failed run(s), all already alerted.")
        return 0

    lines = [
        "ALERTA: pipeline com falha",
        "",
    ]
    for run in new_failures:
        slug = run.get("run_slug", "?")
        category = run.get("category", "?")
        updated = run.get("updated_at", "?")
        lines.append(f"- {slug} ({category}) - updated: {updated}")
        alerted.add(slug)

    lines.append("")
    lines.append("Verifique e resolva manualmente ou resete:")
    lines.append("  python3 tools/gate_decision.py --run-slug <slug> --action reset_to_gate2")

    message = "\n".join(lines)
    print(message)
    send_telegram(message, message_kind="failure")
    save_alerted(alerted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
