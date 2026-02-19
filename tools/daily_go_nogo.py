#!/usr/bin/env python3
"""
Daily GO/NO-GO Telegram notification.

Replaces n8n Workflow 1: fetches latest pipeline run from the control plane
and sends a summary to Telegram with gate status and commands to approve/reject.

Schedule: 09:05 America/Sao_Paulo (via launchagent or cron).

Required env vars:
  CONTROL_PLANE_URL    - e.g. https://new-project-control-plane.vercel.app
  OPS_READ_SECRET      - Bearer token for /api/ops/runs
  TELEGRAM_CHAT_ID     - Telegram chat to send to
  OPENCLAW_TELEGRAM_ACCOUNT - (optional, default: tg_main)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.control_plane import api_get, send_telegram


def gate_emoji(approved: object) -> str:
    if approved is None:
        return "pending"
    if isinstance(approved, bool):
        return "approved" if approved else "rejected"
    return "approved" if bool(approved) else "rejected"


def build_message(runs: list) -> str:
    if not runs:
        return (
            "Daily GO/NO-GO\n\n"
            "Nenhum run encontrado. Nada para aprovar hoje.\n\n"
            "Dica: rode o pipeline com --phase gate1 para criar um run."
        )

    run = runs[0]
    slug = run.get("run_slug", "?")
    status = run.get("status", "?")
    category = run.get("category", "?")
    g1 = gate_emoji(run.get("gate1_approved"))
    g2 = gate_emoji(run.get("gate2_approved"))
    g1_reviewer = run.get("gate1_reviewer") or "-"
    g2_reviewer = run.get("gate2_reviewer") or "-"
    updated = run.get("updated_at", "?")

    lines = [
        "Daily GO/NO-GO",
        "",
        f"Run: {slug}",
        f"Categoria: {category}",
        f"Status: {status}",
        f"Gate 1: {g1} (reviewer: {g1_reviewer})",
        f"Gate 2: {g2} (reviewer: {g2_reviewer})",
        f"Atualizado: {updated}",
        "",
    ]

    if status == "draft_ready_waiting_gate_1" and g1 == "pending":
        lines.append("Acao necessaria: aprovar ou rejeitar Gate 1.")
        lines.append(f"  python3 tools/gate_decision.py --run-slug {slug} --gate gate1 --decision approve")
        lines.append(f"  python3 tools/gate_decision.py --run-slug {slug} --gate gate1 --decision reject")
    elif status == "assets_ready_waiting_gate_2" and g2 == "pending":
        lines.append("Acao necessaria: aprovar ou rejeitar Gate 2.")
        lines.append(f"  python3 tools/gate_decision.py --run-slug {slug} --gate gate2 --decision approve")
        lines.append(f"  python3 tools/gate_decision.py --run-slug {slug} --gate gate2 --decision reject")
    elif status == "published":
        lines.append("Run publicado com sucesso.")
    elif status == "failed":
        lines.append("ATENCAO: run com status FAILED.")
    else:
        lines.append(f"Status atual: {status}. Nenhuma acao necessaria agora.")

    if len(runs) > 1:
        lines.append("")
        lines.append(f"(+{len(runs) - 1} outros runs recentes)")

    return "\n".join(lines)


def main() -> int:
    try:
        data = api_get("/api/ops/runs", "OPS_READ_SECRET", params={"limit": "5"})
    except Exception as e:
        msg = f"Daily GO/NO-GO - ERRO\n\nNao consegui consultar runs:\n{e}"
        send_telegram(msg)
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    runs = data.get("rows", [])
    message = build_message(runs)
    print(message)

    ok = send_telegram(message, message_kind="gate")
    if not ok:
        print("WARNING: Telegram send failed or skipped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
