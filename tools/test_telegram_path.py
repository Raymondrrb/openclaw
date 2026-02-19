#!/usr/bin/env python3
"""
Smoke test: control-plane -> (optional MiniMax rewrite) -> Telegram send.

Usage examples:
  python3 tools/test_telegram_path.py --kind gate
  python3 tools/test_telegram_path.py --kind failure --message "ALERTA: teste manual"
  python3 tools/test_telegram_path.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.common import now_iso, load_env_file
from lib.control_plane import api_get, send_telegram


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Smoke test for Telegram notification path")
    p.add_argument("--kind", choices=["gate", "failure", "summary", "generic"], default="generic")
    p.add_argument("--message", default="", help="Optional explicit message")
    p.add_argument("--dry-run", action="store_true", help="Do not send to Telegram")
    p.add_argument("--load-openclaw-env", action="store_true", default=True,
                   help="Load /Users/ray/Documents/openclaw/.env when present")
    p.add_argument("--no-load-openclaw-env", dest="load_openclaw_env", action="store_false")
    return p.parse_args()


def _bootstrap_env(load_openclaw_env: bool) -> None:
    load_env_file(os.path.expanduser("~/.config/newproject/ops.env"))
    load_env_file(os.path.expanduser("~/.config/newproject/minimax.env"))
    if load_openclaw_env:
        load_env_file("/Users/ray/Documents/openclaw/.env")


def _default_message(kind: str) -> str:
    if kind == "failure":
        return (
            "ALERTA: smoke test de failure alert\n"
            "Run: smoke_test_telegram\n"
            "Acao: validar envio e formato."
        )
    if kind == "gate":
        return (
            "Gate decision pending (smoke test)\n"
            "Run: smoke_test_telegram\n"
            "Ação necessária: approve gate2."
        )
    if kind == "summary":
        try:
            summary = api_get("/api/ops/summary", "OPS_READ_SECRET")
            c = summary.get("counts", {})
            return (
                "Resumo executivo (smoke test)\n"
                f"Policies: {c.get('policies', '?')}\n"
                f"Missions: {c.get('missions', '?')}\n"
                f"Steps: {c.get('steps', '?')}\n"
                f"Events: {c.get('events', '?')}\n"
                f"TS: {now_iso()}"
            )
        except Exception as e:
            return f"Resumo executivo (smoke test) sem dados da API: {e}"
    return f"Teste Telegram path ({kind}) - {now_iso()}"


def main() -> int:
    args = parse_args()
    _bootstrap_env(args.load_openclaw_env)
    msg = args.message.strip() or _default_message(args.kind)

    print(f"[INFO] kind={args.kind} dry_run={args.dry_run}")
    print(f"[INFO] minimax_enabled={os.environ.get('TELEGRAM_USE_MINIMAX', '')!r}")
    print(f"[INFO] chat_id_set={bool(os.environ.get('TELEGRAM_CHAT_ID', '').strip())}")
    print(f"[INFO] control_plane_url_set={bool(os.environ.get('CONTROL_PLANE_URL', '').strip())}")

    if args.dry_run:
        print("[DRY RUN] message preview:")
        print(msg)
        return 0

    ok = send_telegram(msg, message_kind=args.kind)
    if not ok:
        print("[FAIL] Telegram send failed")
        return 1
    print("[OK] Telegram message sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
