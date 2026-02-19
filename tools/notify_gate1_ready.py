#!/usr/bin/env python3
"""
Send a Telegram notification when a Gate 1 package is ready.

This is intentionally simple and relies on OpenClaw's Telegram channel config.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple


BASE_DIR = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent))
RUNS_DIR = BASE_DIR / "content" / "pipeline_runs"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Notify Gate 1 readiness via OpenClaw Telegram.")
    p.add_argument("--date", default=dt.date.today().isoformat(), help="YYYY-MM-DD (default: today)")
    p.add_argument("--chat-id", default="5853624777", help="Telegram chat id")
    p.add_argument("--account", default=os.environ.get("OPENCLAW_TELEGRAM_ACCOUNT", "tg_main"))
    p.add_argument("--channel", default="telegram")
    return p.parse_args()


def find_latest_gate1_for_date(date_str: str) -> Optional[Tuple[str, Path]]:
    if not RUNS_DIR.exists():
        return None
    candidates = []
    for d in RUNS_DIR.glob(f"*_{date_str}"):
        if not d.is_dir():
            continue
        gate1 = d / "gate1_review.md"
        if gate1.exists() and gate1.stat().st_size > 0:
            candidates.append((gate1.stat().st_mtime, d.name, gate1))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    _, run_slug, gate1_path = candidates[0]
    return run_slug, gate1_path


def extract_category(gate1_path: Path) -> str:
    try:
        for raw in gate1_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.lower().startswith("- category:"):
                # "- Category: `Smart rings`"
                return line.split(":", 1)[1].strip().strip("`")
    except Exception:
        pass
    return ""


def main() -> None:
    args = parse_args()
    if str(args.date).strip().upper() == "TODAY":
        args.date = dt.date.today().isoformat()

    found = find_latest_gate1_for_date(args.date)
    if not found:
        payload = {"ok": False, "reason": "no_gate1_found", "date": args.date}
        print(json.dumps(payload, indent=2))
        raise SystemExit(2)

    run_slug, gate1_path = found
    category = extract_category(gate1_path) or "categoria do dia"

    msg = (
        "Gate 1 pronto (Top 5 + roteiro).\n"
        f"- Categoria: {category}\n"
        f"- run_slug: {run_slug}\n"
        f"- Arquivo: {gate1_path}\n\n"
        "Aprovar/rejeitar Gate 1 antes de gerar assets pagos (Dzine/voz/render/upload)."
    )

    cmd = [
        "openclaw",
        "message",
        "send",
        "--channel",
        args.channel,
        "--account",
        args.account,
        "--target",
        args.chat_id,
        "--message",
        msg,
        "--json",
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    ok = p.returncode == 0
    payload = {
        "ok": ok,
        "date": args.date,
        "run_slug": run_slug,
        "gate1_review": str(gate1_path),
        "category": category,
        "send_stdout": (p.stdout or "").strip()[:400],
        "send_stderr": (p.stderr or "").strip()[:400],
    }
    print(json.dumps(payload, indent=2))
    if not ok:
        raise SystemExit(p.returncode)


if __name__ == "__main__":
    main()

