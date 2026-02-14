"""Telegram Gate — atomic, idempotent approval handler for circuit breaker pauses.

Sends inline buttons (Refetch / Ignore / Abort) when the circuit breaker
trips on critical claims. Each button action is:
    - Atomic: CAS update (WHERE status='waiting_approval' AND approval_nonce=?)
    - Idempotent: UNIQUE(run_id, action_id) prevents double-click duplication
    - Auditable: every action logged to run_events with full payload

Integration:
    - Uses control_plane.send_telegram() for message delivery
    - Uses run_manager.RunManager for state transitions
    - Callbacks carry: action:<run_id>:<approval_nonce>:<action_id>

Stdlib only.

Usage:
    from lib.telegram_gate import send_gate_message, handle_gate_callback

    # When CB trips:
    send_gate_message(run_id, nonce, gate_reason, weak_claims)

    # When button pressed (webhook/polling):
    result = handle_gate_callback(callback_data, run_manager)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any


# ---------------------------------------------------------------------------
# Telegram API helpers
# ---------------------------------------------------------------------------

def _bot_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _chat_id() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def _api_call(method: str, payload: dict) -> dict | None:
    """Call Telegram Bot API. Returns response dict or None on failure."""
    token = _bot_token()
    if not token:
        print("[telegram_gate] TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        return None

    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, method="POST",
        headers={"Content-Type": "application/json"},
        data=data,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"[telegram_gate] API call {method} failed: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Gate message — sends inline keyboard buttons
# ---------------------------------------------------------------------------

def send_gate_message(
    run_id: str,
    nonce: str,
    gate_reason: str,
    *,
    weak_claims: list[dict] | None = None,
    video_id: str = "",
) -> bool:
    """Send a Telegram message with Refetch / Ignore / Abort buttons.

    Button callback data format: "action:run_id:nonce:action_id"
    Each click gets a unique action_id for idempotency.

    Returns True if message was sent.
    """
    chat = _chat_id()
    if not chat or not _bot_token():
        print("[telegram_gate] Telegram not configured, skipping gate message", file=sys.stderr)
        return False

    # Build message text
    header = "[Rayviews Lab] Circuit Breaker"
    if video_id:
        header = f"[Rayviews Lab] {video_id} — Circuit Breaker"

    lines = [
        header,
        "",
        f"Run paused: {gate_reason}",
    ]

    if weak_claims:
        lines.append("")
        lines.append("Weak claims:")
        for wc in weak_claims[:5]:
            ct = wc.get("claim_type", "?")
            score = wc.get("score", 0)
            reason = wc.get("weakness_reason", "")
            lines.append(f"  - {ct}: score={score:.2f} ({reason})")

    lines.append("")
    lines.append("Choose action:")

    text = "\n".join(lines)

    # Build inline keyboard — each button has a unique action_id
    refetch_aid = str(uuid.uuid4())[:8]
    ignore_aid = str(uuid.uuid4())[:8]
    abort_aid = str(uuid.uuid4())[:8]

    keyboard = {
        "inline_keyboard": [[
            {
                "text": "Refetch",
                "callback_data": f"refetch:{run_id}:{nonce}:{refetch_aid}",
            },
            {
                "text": "Ignore",
                "callback_data": f"ignore:{run_id}:{nonce}:{ignore_aid}",
            },
            {
                "text": "Abort",
                "callback_data": f"abort:{run_id}:{nonce}:{abort_aid}",
            },
        ]],
    }

    result = _api_call("sendMessage", {
        "chat_id": chat,
        "text": text,
        "reply_markup": keyboard,
    })

    return result is not None and result.get("ok", False)


# ---------------------------------------------------------------------------
# Callback handler — processes button presses
# ---------------------------------------------------------------------------

def parse_callback_data(data: str) -> dict | None:
    """Parse button callback data string.

    Format: "action:run_id:nonce:action_id"
    Returns: {action, run_id, nonce, action_id} or None if invalid.
    """
    parts = data.split(":")
    if len(parts) != 4:
        return None

    action, run_id, nonce, action_id = parts
    if action not in ("refetch", "ignore", "abort"):
        return None

    return {
        "action": action,
        "run_id": run_id,
        "nonce": nonce,
        "action_id": action_id,
    }


def handle_gate_callback(
    callback_data: str,
    run_manager: Any,
    *,
    refetch_fn: Any | None = None,
) -> dict:
    """Handle a Telegram inline button callback.

    Args:
        callback_data: The callback_data string from Telegram.
        run_manager: RunManager instance for the run.
        refetch_fn: Optional callable that re-fetches evidence. Returns new list.

    Returns:
        {"ok": bool, "action": str, "message": str}
    """
    parsed = parse_callback_data(callback_data)
    if not parsed:
        return {"ok": False, "action": "", "message": "Invalid callback data"}

    action = parsed["action"]
    run_id = parsed["run_id"]
    nonce = parsed["nonce"]
    action_id = parsed["action_id"]

    # Verify run_id matches
    if run_manager.run_id != run_id:
        return {"ok": False, "action": action, "message": "Run ID mismatch"}

    # Handle each action
    if action == "refetch":
        return _handle_refetch(run_manager, nonce, action_id, refetch_fn)
    elif action == "ignore":
        return _handle_ignore(run_manager, nonce, action_id)
    elif action == "abort":
        return _handle_abort(run_manager, nonce, action_id)
    else:
        return {"ok": False, "action": action, "message": f"Unknown action: {action}"}


def _handle_refetch(
    rm: Any,
    nonce: str,
    action_id: str,
    refetch_fn: Any | None,
) -> dict:
    """Handle 'refetch' button: re-fetch evidence, re-evaluate CB."""
    if not refetch_fn:
        return {"ok": False, "action": "refetch", "message": "No refetch_fn configured"}

    # First approve (to unlock the run)
    ok = rm.approve(nonce, action_id)
    if not ok:
        return {
            "ok": False,
            "action": "refetch",
            "message": "CAS failed — state already changed or nonce mismatch",
        }

    # Execute refetch
    try:
        new_evidence = refetch_fn()
    except Exception as exc:
        rm.fail(f"Refetch failed: {exc}")
        return {"ok": False, "action": "refetch", "message": f"Refetch error: {exc}"}

    # Re-evaluate with fresh evidence
    result = rm.evaluate_and_gate(new_evidence, refetch_fn=refetch_fn)

    if result.should_gate:
        return {
            "ok": True,
            "action": "refetch",
            "message": f"Refetch done but still gated: {result.gate_reason}",
        }

    return {"ok": True, "action": "refetch", "message": "Refetch resolved weakness, continuing"}


def _handle_ignore(rm: Any, nonce: str, action_id: str) -> dict:
    """Handle 'ignore' button: proceed despite low confidence."""
    ok = rm.ignore_weakness(nonce, action_id)
    if not ok:
        return {
            "ok": False,
            "action": "ignore",
            "message": "CAS failed — state already changed or nonce mismatch",
        }
    return {"ok": True, "action": "ignore", "message": "Weakness ignored, continuing"}


def _handle_abort(rm: Any, nonce: str, action_id: str) -> dict:
    """Handle 'abort' button: abort the run."""
    ok = rm.abort_by_user(nonce, action_id, reason="User abort via Telegram")
    if not ok:
        return {
            "ok": False,
            "action": "abort",
            "message": "CAS failed — state already changed or nonce mismatch",
        }
    return {"ok": True, "action": "abort", "message": "Run aborted by user"}


# ---------------------------------------------------------------------------
# Callback answer (acknowledge button press)
# ---------------------------------------------------------------------------

def answer_callback(callback_query_id: str, text: str = "") -> bool:
    """Answer a Telegram callback query (dismiss loading indicator)."""
    result = _api_call("answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text or "Processing...",
    })
    return result is not None and result.get("ok", False)
