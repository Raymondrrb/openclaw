"""Pipeline Approval Gates — blocking Telegram approval for pipeline decisions.

Sends inline buttons [Approve] / [Reject] and polls for a response.
Used for critical pipeline decisions (product selection, script approval)
before committing to expensive downstream work.

Callback data format: pa:<gate_name>:<8-char-uuid>:approve|reject
Prefix "pa:" avoids collision with circuit breaker ("refetch:", "ignore:", "abort:").

Graceful degradation:
    - skip=True or PIPELINE_NO_APPROVAL=1  → auto-approve
    - Telegram not configured              → auto-approve + stderr warning
    - Network error on send                → auto-approve + stderr warning
    - Network error on poll                → retry with backoff
    - Timeout (default 30 min)             → reject (returns False)

Stdlib only.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid


# ---------------------------------------------------------------------------
# Telegram helpers (mirrored from telegram_gate.py — standalone)
# ---------------------------------------------------------------------------

_PLACEHOLDER_TOKENS = {
    "summary",
    "detail",
    "details",
    "test",
    "todo",
    "tbd",
    "na",
    "n/a",
}

def _bot_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _chat_id() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def _is_configured() -> bool:
    return bool(_bot_token()) and bool(_chat_id())


def _api_call(method: str, payload: dict) -> dict | None:
    """Call Telegram Bot API. Returns parsed response dict or None on error."""
    token = _bot_token()
    if not token:
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
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        print(f"[pipeline_approval] API {method} failed: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Low-level operations
# ---------------------------------------------------------------------------

def _get_webhook_url() -> str:
    """Get the current webhook URL (empty string if none set)."""
    resp = _api_call("getWebhookInfo", {})
    if resp and resp.get("ok"):
        return resp.get("result", {}).get("url", "")
    return ""


def _drop_webhook() -> str:
    """Delete the active webhook so getUpdates works. Returns old URL.

    Always calls deleteWebhook even if getWebhookInfo reports empty URL,
    because a prior getUpdates conflict (409) can persist otherwise.
    """
    old_url = _get_webhook_url()
    _api_call("deleteWebhook", {"drop_pending_updates": False})
    return old_url


def _restore_webhook(url: str) -> None:
    """Restore a previously active webhook."""
    if url:
        _api_call("setWebhook", {"url": url})


def _flush_updates() -> int | None:
    """Consume all pending updates and return the last update_id.

    Calls getUpdates(offset=-1, limit=1) to jump to the end.
    Returns the last update_id (to use as offset base) or None.
    """
    resp = _api_call("getUpdates", {"offset": -1, "limit": 1, "timeout": 0})
    if not resp or not resp.get("ok"):
        return None
    results = resp.get("result", [])
    if results:
        return results[-1]["update_id"]
    return None


def _send_approval_message(
    text: str, approve_data: str, reject_data: str,
) -> int | None:
    """Send a message with [Approve] / [Reject] inline keyboard.

    Returns the message_id on success, None on failure.
    """
    chat = _chat_id()
    if not chat:
        return None

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Aprovar", "callback_data": approve_data},
            {"text": "❌ Rejeitar", "callback_data": reject_data},
        ]],
    }

    resp = _api_call("sendMessage", {
        "chat_id": chat,
        "text": text,
        "reply_markup": keyboard,
    })
    if resp and resp.get("ok"):
        return resp["result"]["message_id"]
    return None


def _answer_callback(callback_query_id: str, text: str) -> None:
    """Acknowledge a callback query (dismiss the loading spinner)."""
    _api_call("answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text,
    })


def _edit_message_text(message_id: int, new_text: str) -> None:
    """Edit the text of an existing message (removes inline keyboard)."""
    chat = _chat_id()
    if not chat:
        return
    _api_call("editMessageText", {
        "chat_id": chat,
        "message_id": message_id,
        "text": new_text,
    })


def _poll_for_response(
    message_id: int,
    approve_data: str,
    reject_data: str,
    offset: int | None,
    timeout_s: int,
) -> str | None:
    """Long-poll for a callback_query matching our message.

    Returns "approve", "reject", or None on timeout.
    """
    deadline = time.monotonic() + timeout_s
    poll_offset = (offset + 1) if offset is not None else None
    backoff = 0.0

    while time.monotonic() < deadline:
        params: dict = {
            "timeout": 3,
            "allowed_updates": ["callback_query"],
        }
        if poll_offset is not None:
            params["offset"] = poll_offset

        resp = _api_call("getUpdates", params)

        if resp is None:
            # Network error — back off and retry
            backoff = min(backoff + 2.0, 10.0)
            time.sleep(backoff)
            continue

        backoff = 0.0
        updates = resp.get("result", [])

        for upd in updates:
            poll_offset = upd["update_id"] + 1
            cb = upd.get("callback_query")
            if not cb:
                continue
            msg = cb.get("message", {})
            if msg.get("message_id") != message_id:
                continue
            data = cb.get("data", "")
            cq_id = cb.get("id", "")

            if data == approve_data:
                _answer_callback(cq_id, "Aprovado ✅")
                return "approve"
            elif data == reject_data:
                _answer_callback(cq_id, "Rejeitado ❌")
                return "reject"

    return None  # timeout


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def request_approval(
    gate_name: str,
    summary: str,
    details: list[str] | str,
    *,
    video_id: str = "",
    timeout_s: int = 1800,
    skip: bool = False,
) -> bool:
    """Request Telegram approval. Blocks until Approve/Reject/timeout.

    Args:
        gate_name: Short identifier (e.g. "products", "script").
        summary: One-line summary shown in the message header.
        details: List of detail lines (or a single string).
        video_id: For display in the message header.
        timeout_s: Seconds to wait before auto-rejecting (default 30 min).
        skip: If True, auto-approve immediately.

    Returns:
        True  → approved (or skipped / not configured / send error)
        False → rejected or timed out
    """
    # Skip gates
    if skip:
        return True
    if os.environ.get("PIPELINE_NO_APPROVAL", "").strip() == "1":
        return True

    # Telegram not configured → auto-approve with warning
    if not _is_configured():
        print(
            f"[pipeline_approval] Telegram not configured — auto-approving '{gate_name}'",
            file=sys.stderr,
        )
        return True

    # Build message text
    normalized_summary = _normalize_summary(gate_name, summary)
    normalized_details = _normalize_details(gate_name, details)

    header = f"🧭 RayViewsLab Approval\nGate: {gate_name.upper()}\nResumo: {normalized_summary}"
    if video_id:
        header = (
            "🧭 RayViewsLab Approval\n"
            f"Gate: {gate_name.upper()}\n"
            f"Run: {video_id}\n"
            f"Resumo: {normalized_summary}"
        )

    body = "\n".join(f"• {line}" for line in normalized_details)

    text = f"{header}\n\n{body}"

    # Callback data
    uid = str(uuid.uuid4())[:8]
    approve_data = f"pa:{gate_name}:{uid}:approve"
    reject_data = f"pa:{gate_name}:{uid}:reject"

    # Drop webhook so getUpdates works (409 Conflict otherwise)
    old_webhook = _drop_webhook()
    time.sleep(0.5)  # let Telegram release polling lock

    try:
        # Flush old updates
        last_update_id = _flush_updates()

        # Send message
        msg_id = _send_approval_message(text, approve_data, reject_data)
        if msg_id is None:
            print(
                f"[pipeline_approval] Failed to send message — auto-approving '{gate_name}'",
                file=sys.stderr,
            )
            return True

        print(f"\nWaiting for Telegram approval ({gate_name})...")

        # Poll
        result = _poll_for_response(msg_id, approve_data, reject_data, last_update_id, timeout_s)

        if result == "approve":
            _edit_message_text(msg_id, f"{text}\n\n✅ DECISÃO: APROVADO")
            print(f"  {gate_name}: APPROVED")
            return True
        elif result == "reject":
            _edit_message_text(msg_id, f"{text}\n\n❌ DECISÃO: REJEITADO")
            print(f"  {gate_name}: REJECTED")
            return False
        else:
            _edit_message_text(msg_id, f"{text}\n\n⏰ DECISÃO: TEMPO ESGOTADO")
            print(f"  {gate_name}: TIMED OUT")
            return False
    finally:
        _restore_webhook(old_webhook)


def _normalize_summary(gate_name: str, summary: str) -> str:
    raw = str(summary or "").strip()
    if not raw or raw.lower() in _PLACEHOLDER_TOKENS:
        return f"Approval required for {gate_name}"
    return raw


def _normalize_details(gate_name: str, details: list[str] | str) -> list[str]:
    if isinstance(details, str):
        source = [details]
    else:
        source = list(details or [])

    cleaned: list[str] = []
    for line in source:
        text = str(line or "").strip()
        if not text:
            continue
        if text.lower() in _PLACEHOLDER_TOKENS:
            continue
        cleaned.append(text)

    if cleaned:
        return cleaned
    return [f"Review gate payload '{gate_name}' before approving."]
