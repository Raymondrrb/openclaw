"""Helpers for calling the Vercel control plane API and sending Telegram messages."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def control_plane_url() -> str:
    """Base URL for the Vercel control plane."""
    return os.environ.get("CONTROL_PLANE_URL", "").rstrip("/")


def api_get(path: str, secret_name: str, *, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """GET request to the control plane API."""
    base = control_plane_url()
    if not base:
        raise RuntimeError("Missing CONTROL_PLANE_URL env var")
    secret = os.environ.get(secret_name, "").strip()
    if not secret:
        raise RuntimeError(f"Missing {secret_name} env var")

    url = f"{base}{path}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)

    req = Request(url, method="GET", headers={
        "Authorization": f"Bearer {secret}",
        "Accept": "application/json",
    })
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body_text}") from e


def api_post(path: str, secret_name: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """POST request to the control plane API."""
    base = control_plane_url()
    if not base:
        raise RuntimeError("Missing CONTROL_PLANE_URL env var")
    secret = os.environ.get(secret_name, "").strip()
    if not secret:
        raise RuntimeError(f"Missing {secret_name} env var")

    url = f"{base}{path}"
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method="POST", headers={
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body_text}") from e


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _minimax_cfg() -> Dict[str, str]:
    cfg = {
        "api_key": "",
        "model": "MiniMax-M2.5",
        "base_url": "https://api.minimax.io/v1",
    }
    env_file = Path(os.path.expanduser("~/.config/newproject/minimax.env"))
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            key = k.strip()
            val = v.strip()
            if key == "MINIMAX_API_KEY":
                cfg["api_key"] = val
            elif key == "MINIMAX_MODEL":
                cfg["model"] = val
            elif key == "MINIMAX_BASE_URL":
                cfg["base_url"] = val
    cfg["api_key"] = os.environ.get("MINIMAX_API_KEY", cfg["api_key"]).strip()
    cfg["model"] = os.environ.get("MINIMAX_MODEL", cfg["model"]).strip() or cfg["model"]
    cfg["base_url"] = os.environ.get("MINIMAX_BASE_URL", cfg["base_url"]).strip() or cfg["base_url"]
    return cfg


def _minimax_template_for_kind(message_kind: str, explicit_template: str = "") -> str:
    if explicit_template.strip():
        return explicit_template.strip()

    kind = str(message_kind or "generic").strip().lower()
    specific = os.environ.get(f"TELEGRAM_MINIMAX_TEMPLATE_{kind.upper()}", "").strip()
    if specific:
        return specific

    fallback_default = os.environ.get("TELEGRAM_MINIMAX_TEMPLATE_DEFAULT", "").strip()
    if fallback_default:
        return fallback_default

    base = (
        "You rewrite ops notifications for Telegram.\n"
        "Keep it concise and clear in Brazilian Portuguese.\n"
        "Preserve all commands, URLs, IDs, numbers, and line breaks that contain shell commands.\n"
        "Do not invent facts, statuses, or actions."
    )
    by_kind = {
        "gate": "Lead with required human action and gate status in the first line.",
        "failure": "Start with 'ALERTA' and keep the critical failure reason in line 1.",
        "summary": "Use compact bullet-like lines with key counts and one clear takeaway.",
        "generic": "Keep neutral operational tone.",
    }
    return base + "\n" + by_kind.get(kind, by_kind["generic"])


def _default_telegram_rewrite_log_path() -> Path:
    custom = os.environ.get("TELEGRAM_REWRITE_LOG_PATH", "").strip()
    if custom:
        return Path(os.path.expanduser(custom)).resolve()
    return (Path(__file__).resolve().parents[2] / "tmp" / "telegram_rewrites.jsonl").resolve()


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def _maybe_log_telegram_message(
    *,
    message_kind: str,
    raw_message: str,
    final_message: str,
    rewrite_applied: bool,
    rewrite_status: str,
    send_ok: bool,
) -> None:
    if not (_truthy(os.environ.get("TELEGRAM_LOG_MESSAGES", "")) or _truthy(os.environ.get("TELEGRAM_USE_MINIMAX", ""))):
        return
    row = {
        "ts": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "kind": str(message_kind or "generic"),
        "rewrite_applied": bool(rewrite_applied),
        "rewrite_status": rewrite_status,
        "send_ok": bool(send_ok),
        "raw_len": len(raw_message),
        "final_len": len(final_message),
        "raw_sha256": hashlib.sha256(raw_message.encode("utf-8")).hexdigest(),
        "final_sha256": hashlib.sha256(final_message.encode("utf-8")).hexdigest(),
        "raw_message": raw_message,
        "final_message": final_message,
    }
    try:
        _append_jsonl(_default_telegram_rewrite_log_path(), row)
    except Exception as e:
        print(f"WARNING: failed to write telegram rewrite log ({e})")


def _minimax_rewrite_telegram(
    message: str,
    *,
    message_kind: str = "generic",
    minimax_template: str = "",
) -> str:
    cfg = _minimax_cfg()
    if not cfg["api_key"]:
        raise RuntimeError("MINIMAX_API_KEY not configured")

    system = _minimax_template_for_kind(message_kind, minimax_template)
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
        "max_tokens": 800,
        "temperature": 0.35,
    }
    req = Request(
        f"{cfg['base_url'].rstrip('/')}/chat/completions",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
    )
    with urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("MiniMax returned no choices")
    text = str(choices[0].get("message", {}).get("content", "")).strip()
    if not text:
        raise RuntimeError("MiniMax returned empty content")
    return text


def send_telegram(
    message: str,
    *,
    chat_id: str = "",
    account: str = "",
    message_kind: str = "generic",
    minimax_template: str = "",
) -> bool:
    """Send a Telegram message via OpenClaw CLI."""
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    account = account or os.environ.get("OPENCLAW_TELEGRAM_ACCOUNT", "tg_main")

    if not chat_id:
        print("WARNING: No TELEGRAM_CHAT_ID set, skipping Telegram send")
        return False

    final_message = message
    rewrite_applied = False
    rewrite_status = "disabled"
    if _truthy(os.environ.get("TELEGRAM_USE_MINIMAX", "")):
        try:
            final_message = _minimax_rewrite_telegram(
                message,
                message_kind=message_kind,
                minimax_template=minimax_template,
            )
            rewrite_applied = True
            rewrite_status = "ok"
        except Exception as e:  # Fail open; do not block Telegram alerts.
            rewrite_status = "fallback_raw"
            print(f"WARNING: MiniMax rewrite failed, sending raw message ({e})")

    cmd = [
        "openclaw", "message", "send",
        "--channel", "telegram",
        "--account", account,
        "--target", chat_id,
        "--message", final_message,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    ok = result.returncode == 0
    _maybe_log_telegram_message(
        message_kind=message_kind,
        raw_message=message,
        final_message=final_message,
        rewrite_applied=rewrite_applied,
        rewrite_status=rewrite_status,
        send_ok=ok,
    )
    return ok
