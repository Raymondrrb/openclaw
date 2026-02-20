"""Telegram Image Approval — blocking approval gate for Dzine product images.

Sends product images as Telegram albums (sendMediaGroup) with inline
[Approve All] / [Reject] buttons and polls for a response.

On rejection, prompts user for specific labels to reject via text reply.

Callback data format: ia:<gate>:<8-char-uuid>:approve|reject
Prefix "ia:" avoids collision with pipeline_approval ("pa:") and circuit breaker.

Graceful degradation:
    - skip=True or PIPELINE_NO_APPROVAL=1  → auto-approve all
    - Telegram not configured              → auto-approve all + stderr warning
    - Network error on send                → auto-approve all + stderr warning
    - Network error on poll                → retry with backoff
    - Timeout (default 30 min)             → reject all (conservative)

Stdlib only.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from tools.lib.control_plane import send_telegram, send_telegram_media


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ImageEntry:
    label: str           # "01_hero"
    path: Path           # absolute path to .png
    product_name: str    # "Roborock Q7 M5+"
    variant: str         # "hero"


@dataclass
class ImageApprovalResult:
    approved: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)

    @property
    def all_approved(self) -> bool:
        return len(self.rejected) == 0


# ---------------------------------------------------------------------------
# Telegram helpers (mirrored from pipeline_approval.py — standalone)
# ---------------------------------------------------------------------------

def _bot_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _chat_id() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def _is_configured() -> bool:
    return bool(_bot_token()) and bool(_chat_id())


def _openclaw_channel_ready() -> bool:
    return bool(_chat_id()) and shutil.which("openclaw") is not None


def _api_call(method: str, payload: dict) -> dict | None:
    """Call Telegram Bot API with JSON payload. Returns parsed response or None."""
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
        print(f"[image_approval] API {method} failed: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Webhook / update management
# ---------------------------------------------------------------------------

def _get_webhook_url() -> str:
    resp = _api_call("getWebhookInfo", {})
    if resp and resp.get("ok"):
        return resp.get("result", {}).get("url", "")
    return ""


def _drop_webhook() -> str:
    old_url = _get_webhook_url()
    _api_call("deleteWebhook", {"drop_pending_updates": False})
    return old_url


def _restore_webhook(url: str) -> None:
    if url:
        _api_call("setWebhook", {"url": url})


def _flush_updates() -> int | None:
    resp = _api_call("getUpdates", {"offset": -1, "limit": 1, "timeout": 0})
    if not resp or not resp.get("ok"):
        return None
    results = resp.get("result", [])
    if results:
        return results[-1]["update_id"]
    return None


# ---------------------------------------------------------------------------
# Photo sending (multipart/form-data — stdlib)
# ---------------------------------------------------------------------------

def _build_multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    """Build multipart/form-data body.

    Args:
        fields: {field_name: value} for text fields
        files: {field_name: (filename, data, content_type)} for file fields

    Returns:
        (body_bytes, boundary)
    """
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []

    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode())

    for name, (filename, data, content_type) in files.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        parts.append(data)
        parts.append(b"\r\n")

    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def _send_photo(image_path: str | Path, caption: str = "") -> int | None:
    """Send a single photo via Telegram sendPhoto (multipart upload).

    Returns message_id on success, None on failure.
    """
    token = _bot_token()
    chat = _chat_id()
    if not token or not chat:
        return None

    path = Path(image_path)
    if not path.is_file():
        print(f"[image_approval] File not found: {path}", file=sys.stderr)
        return None

    photo_data = path.read_bytes()
    fields = {"chat_id": chat}
    if caption:
        fields["caption"] = caption

    files = {"photo": (path.name, photo_data, "image/png")}
    body, boundary = _build_multipart(fields, files)

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    req = urllib.request.Request(
        url, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        data=body,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                return result["result"]["message_id"]
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        print(f"[image_approval] sendPhoto failed: {exc}", file=sys.stderr)

    return None


def _send_media_group(images: list[ImageEntry], group_caption: str = "") -> int | None:
    """Send images as a Telegram album (sendMediaGroup, multipart upload).

    Sends up to 10 photos per call. Returns first message_id or None.
    """
    token = _bot_token()
    chat = _chat_id()
    if not token or not chat:
        return None

    if not images:
        return None

    # Telegram limit: 10 photos per media group
    batch = images[:10]

    # Build media JSON array and file fields
    media_array: list[dict] = []
    file_fields: dict[str, tuple[str, bytes, str]] = {}

    for i, entry in enumerate(batch):
        path = Path(entry.path)
        if not path.is_file():
            continue

        attach_key = f"photo_{i}"
        media_item: dict = {
            "type": "photo",
            "media": f"attach://{attach_key}",
        }
        # Caption only on first photo
        if i == 0 and group_caption:
            media_item["caption"] = group_caption

        media_array.append(media_item)
        file_fields[attach_key] = (path.name, path.read_bytes(), "image/png")

    if not media_array:
        return None

    text_fields = {
        "chat_id": chat,
        "media": json.dumps(media_array),
    }

    body, boundary = _build_multipart(text_fields, file_fields)

    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"
    req = urllib.request.Request(
        url, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        data=body,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            if result.get("ok") and result.get("result"):
                return result["result"][0]["message_id"]
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        print(f"[image_approval] sendMediaGroup failed: {exc}", file=sys.stderr)

    return None


# ---------------------------------------------------------------------------
# Approval message + polling
# ---------------------------------------------------------------------------

def _send_approval_buttons(text: str, approve_data: str, reject_data: str) -> int | None:
    """Send a text message with [Approve All] / [Reject] inline keyboard."""
    chat = _chat_id()
    if not chat:
        return None

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Aprovar tudo", "callback_data": approve_data},
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
    _api_call("answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text,
    })


def _edit_message_text(message_id: int, new_text: str) -> None:
    chat = _chat_id()
    if not chat:
        return
    _api_call("editMessageText", {
        "chat_id": chat,
        "message_id": message_id,
        "text": new_text,
    })


def _poll_for_callback(
    message_id: int,
    approve_data: str,
    reject_data: str,
    offset: int | None,
    timeout_s: int,
) -> tuple[str | None, int | None]:
    """Long-poll for a callback_query matching our message.

    Returns ("approve"|"reject", poll_offset) or (None, poll_offset) on timeout.
    """
    deadline = time.monotonic() + timeout_s
    poll_offset = (offset + 1) if offset is not None else None
    backoff = 0.0

    while time.monotonic() < deadline:
        params: dict = {
            "timeout": 3,
            "allowed_updates": ["callback_query", "message"],
        }
        if poll_offset is not None:
            params["offset"] = poll_offset

        resp = _api_call("getUpdates", params)

        if resp is None:
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
                _answer_callback(cq_id, "Tudo aprovado ✅")
                return "approve", poll_offset
            elif data == reject_data:
                _answer_callback(cq_id, "Envie os labels para rejeitar")
                return "reject", poll_offset

    return None, poll_offset


def _poll_for_text_reply(
    offset: int | None,
    timeout_s: int,
) -> str | None:
    """Poll for a text message from the user (rejection labels).

    Returns the message text or None on timeout.
    """
    deadline = time.monotonic() + timeout_s
    poll_offset = (offset + 1) if offset is not None else offset
    backoff = 0.0

    while time.monotonic() < deadline:
        params: dict = {
            "timeout": 3,
            "allowed_updates": ["message"],
        }
        if poll_offset is not None:
            params["offset"] = poll_offset

        resp = _api_call("getUpdates", params)

        if resp is None:
            backoff = min(backoff + 2.0, 10.0)
            time.sleep(backoff)
            continue

        backoff = 0.0
        updates = resp.get("result", [])

        for upd in updates:
            poll_offset = upd["update_id"] + 1
            msg = upd.get("message")
            if not msg:
                continue
            text = msg.get("text", "").strip()
            if text:
                return text

    return None


def _parse_rejected_labels(text: str, valid_labels: set[str]) -> list[str]:
    """Parse user text into rejected labels.

    Accepts space-separated or comma-separated labels.
    If "all" is in the text, rejects everything.
    """
    if not text:
        return []

    text_lower = text.strip().lower()
    if text_lower in ("all", "todos", "todas", "tudo"):
        return sorted(valid_labels)

    # Split on commas, spaces, or newlines
    tokens = []
    for part in text.replace(",", " ").replace("\n", " ").split():
        tokens.append(part.strip())

    rejected = []
    for token in tokens:
        if token in valid_labels:
            rejected.append(token)
        else:
            # Try case-insensitive
            for lbl in valid_labels:
                if lbl.lower() == token.lower():
                    rejected.append(lbl)
                    break

    return sorted(set(rejected))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def request_image_approval(
    images: list[ImageEntry],
    *,
    video_id: str = "",
    timeout_s: int = 1800,
    skip: bool = False,
) -> ImageApprovalResult:
    """Send product images to Telegram and wait for approval.

    Args:
        images: List of ImageEntry to approve.
        video_id: For display in the message header.
        timeout_s: Seconds to wait before auto-rejecting (default 30 min).
        skip: If True, auto-approve all immediately.

    Returns:
        ImageApprovalResult with approved/rejected labels.
    """
    all_labels = [img.label for img in images]

    # Auto-approve result
    def _auto_approve() -> ImageApprovalResult:
        return ImageApprovalResult(approved=list(all_labels), rejected=[])

    # Auto-reject result
    def _auto_reject() -> ImageApprovalResult:
        return ImageApprovalResult(approved=[], rejected=list(all_labels))

    # Skip gates
    if skip:
        return _auto_approve()
    if os.environ.get("PIPELINE_NO_APPROVAL", "").strip() == "1":
        return _auto_approve()

    if not images:
        return ImageApprovalResult()

    # Telegram not configured → auto-approve with warning
    bot_api_ready = _is_configured()
    channel_ready = _openclaw_channel_ready()
    if not bot_api_ready and not channel_ready:
        print(
            "[image_approval] Telegram not configured (bot+channel unavailable) — auto-approving all images",
            file=sys.stderr,
        )
        return _auto_approve()

    # Fallback path: OpenClaw channel can send media, but cannot poll inline callbacks.
    # We still deliver the generated images to Telegram and auto-approve (unless strict mode).
    if not bot_api_ready and channel_ready:
        caption_header = f"[Rayviews Lab] Image previews ({len(images)})"
        if video_id:
            caption_header += f" — {video_id}"

        sent = 0
        for entry in images:
            line = f"{entry.label} — {entry.product_name} ({entry.variant})"
            if send_telegram_media(str(entry.path), caption=line):
                sent += 1

        detail_lines = [
            f"Sent image previews: {sent}/{len(images)}",
            "Approval mode: auto (OpenClaw channel fallback, no callback polling)",
            "To enforce manual approval here, set PIPELINE_IMAGE_APPROVAL_STRICT=1.",
        ]
        send_telegram(
            caption_header + "\n" + "\n".join(detail_lines),
            message_kind="summary",
        )

        if os.environ.get("PIPELINE_IMAGE_APPROVAL_STRICT", "").strip() == "1":
            print(
                "[image_approval] strict mode enabled with channel fallback — rejecting all images",
                file=sys.stderr,
            )
            return _auto_reject()
        return _auto_approve()

    # Build summary
    header = "🖼️ RayViewsLab — Aprovação de Imagens"
    if video_id:
        header += f"\nRun: {video_id}"

    lines = [f"• {img.label} — {img.product_name} ({img.variant})" for img in images]
    summary = f"{header}\n\nTotal: {len(images)} imagem(ns)\n" + "\n".join(lines)
    summary += "\n\nToque um botão ou envie labels para rejeitar."

    # Callback data
    uid = str(uuid.uuid4())[:8]
    approve_data = f"ia:images:{uid}:approve"
    reject_data = f"ia:images:{uid}:reject"

    # Drop webhook so getUpdates works
    old_webhook = _drop_webhook()
    time.sleep(0.5)

    try:
        last_update_id = _flush_updates()

        # Send images as album(s)
        for i in range(0, len(images), 10):
            batch = images[i:i + 10]
            batch_caption = f"{video_id} — images {i + 1}-{i + len(batch)}" if video_id else ""
            _send_media_group(batch, group_caption=batch_caption)

        # Send approval buttons
        msg_id = _send_approval_buttons(summary, approve_data, reject_data)
        if msg_id is None:
            print(
                "[image_approval] Failed to send approval message — auto-approving",
                file=sys.stderr,
            )
            return _auto_approve()

        print(f"\nWaiting for Telegram image approval ({len(images)} images)...")

        # Poll for callback
        result, poll_offset = _poll_for_callback(
            msg_id, approve_data, reject_data, last_update_id, timeout_s,
        )

        if result == "approve":
            _edit_message_text(msg_id, f"{summary}\n\n--- ALL APPROVED ---")
            print(f"  Images: ALL APPROVED")
            return _auto_approve()

        elif result == "reject":
            # Ask for specific labels
            _edit_message_text(
                msg_id,
                f"{summary}\n\n--- REJEIÇÃO ---\nEnvie labels para rejeitar (ex: 01_hero 04_detail) ou 'all':",
            )

            # Poll for text reply (60s for label entry)
            text_reply = _poll_for_text_reply(poll_offset, timeout_s=60)

            valid_labels = {img.label for img in images}

            if text_reply:
                rejected = _parse_rejected_labels(text_reply, valid_labels)
            else:
                # No reply within 60s → reject all (conservative)
                rejected = list(all_labels)

            if not rejected:
                # User sent text but no valid labels → reject all
                rejected = list(all_labels)

            approved = [lbl for lbl in all_labels if lbl not in rejected]
            result_obj = ImageApprovalResult(approved=approved, rejected=rejected)

            status = f"{len(rejected)} REJEITADAS: {', '.join(rejected)}"
            _edit_message_text(msg_id, f"{summary}\n\n--- {status} ---")
            print(f"  Images: {status}")
            return result_obj

        else:
            # Timeout
            _edit_message_text(msg_id, f"{summary}\n\n--- TEMPO ESGOTADO (todas rejeitadas) ---")
            print(f"  Images: TIMED OUT — all rejected")
            return _auto_reject()

    finally:
        _restore_webhook(old_webhook)
