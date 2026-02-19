#!/usr/bin/env python3
"""
Daily executive summary.

Replaces n8n Workflow 3: fetches /api/ops/summary + /api/ops/runs and sends
a nightly Telegram recap at 21:30.

Required env vars:
  CONTROL_PLANE_URL    - e.g. https://new-project-control-plane.vercel.app
  OPS_READ_SECRET      - Bearer token
  TELEGRAM_CHAT_ID     - Telegram chat to send to
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.common import now_iso, today_iso
from lib.control_plane import api_get, send_telegram


def main() -> int:
    errors = []

    try:
        summary = api_get("/api/ops/summary", "OPS_READ_SECRET")
    except Exception as e:
        summary = None
        errors.append(f"summary: {e}")

    try:
        runs_data = api_get("/api/ops/runs", "OPS_READ_SECRET", params={"limit": "20"})
    except Exception as e:
        runs_data = None
        errors.append(f"runs: {e}")

    lines = [
        f"Resumo executivo - {today_iso()}",
        "",
    ]

    if summary and summary.get("ok"):
        counts = summary.get("counts", {})
        lines.append("Contagem Supabase:")
        lines.append(f"  Policies: {counts.get('policies', '?')}")
        lines.append(f"  Proposals: {counts.get('proposals', '?')}")
        lines.append(f"  Missions: {counts.get('missions', '?')}")
        lines.append(f"  Steps: {counts.get('steps', '?')}")
        lines.append(f"  Events: {counts.get('events', '?')}")
        lines.append("")

    if runs_data and runs_data.get("ok"):
        rows = runs_data.get("rows", [])
        published = [r for r in rows if r.get("status") == "published"]
        failed = [r for r in rows if r.get("status") == "failed"]
        waiting_g1 = [r for r in rows if r.get("status") == "draft_ready_waiting_gate_1"]
        waiting_g2 = [r for r in rows if r.get("status") == "assets_ready_waiting_gate_2"]
        rendering = [r for r in rows if r.get("status") == "rendering"]

        lines.append(f"Video runs (ultimos {len(rows)}):")
        lines.append(f"  Publicados: {len(published)}")
        lines.append(f"  Falhados: {len(failed)}")
        lines.append(f"  Aguardando Gate 1: {len(waiting_g1)}")
        lines.append(f"  Aguardando Gate 2: {len(waiting_g2)}")
        lines.append(f"  Renderizando: {len(rendering)}")
        lines.append("")

        if rows:
            latest = rows[0]
            lines.append(f"Ultimo run: {latest.get('run_slug', '?')}")
            lines.append(f"  Status: {latest.get('status', '?')}")
            lines.append(f"  Categoria: {latest.get('category', '?')}")
            lines.append(f"  Atualizado: {latest.get('updated_at', '?')}")
    else:
        lines.append("Sem dados de runs disponiveis.")

    if errors:
        lines.append("")
        lines.append("Erros ao consultar API:")
        for e in errors:
            lines.append(f"  - {e}")

    lines.append("")
    lines.append(f"Gerado: {now_iso()}")

    message = "\n".join(lines)
    print(message)
    send_telegram(message, message_kind="summary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
