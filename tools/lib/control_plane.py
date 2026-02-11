"""Control-plane notifications (Telegram alerts). Stdlib only."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def send_telegram(message: str, *, parse_mode: str = "HTML") -> bool:
    """Send a Telegram message via Bot API. Returns True on success."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("[telegram] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, skipping", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
    }).encode()

    req = urllib.request.Request(
        url,
        method="POST",
        headers={"Content-Type": "application/json"},
        data=payload,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"[telegram] Failed to send alert: {exc}", file=sys.stderr)
        return False
