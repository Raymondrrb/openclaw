"""Pipeline notification system — Telegram alerts with anti-spam.

Message types: START, PROGRESS, ACTION_REQUIRED, ERROR, HEARTBEAT, SUMMARY.
Every non-heartbeat message includes a "Next:" action line.

Builds on control_plane.send_telegram(). Never crashes on failure.
Stdlib only — no external deps.
"""

from __future__ import annotations

import time
from tools.lib.control_plane import send_telegram
from tools.lib.pipeline_status import (
    VideoStatus,
    get_status,
    mark_notified,
    should_heartbeat,
    _suggest_next_action,
)

# ---------------------------------------------------------------------------
# Message types
# ---------------------------------------------------------------------------

TYPE_START = "start"
TYPE_PROGRESS = "progress"
TYPE_ACTION_REQUIRED = "action_required"
TYPE_ERROR = "error"
TYPE_HEARTBEAT = "heartbeat"
TYPE_SUMMARY = "summary"
TYPE_RATE_LIMITED = "rate_limited"

# Emoji per type
_EMOJI = {
    TYPE_START: "\U0001F680",       # rocket
    TYPE_PROGRESS: "\u2705",        # check
    TYPE_ACTION_REQUIRED: "\u26A0\uFE0F",  # warning
    TYPE_ERROR: "\u274C",           # cross
    TYPE_HEARTBEAT: "\U0001F493",   # heartbeat
    TYPE_SUMMARY: "\U0001F3C1",     # flag
    TYPE_RATE_LIMITED: "\u23F3",    # hourglass
}

# Anti-spam: minimum seconds between same-type notifications per video
_THROTTLE_SECONDS = {
    TYPE_START: 0,
    TYPE_PROGRESS: 30,
    TYPE_ACTION_REQUIRED: 60,
    TYPE_ERROR: 30,
    TYPE_HEARTBEAT: 480,  # 8 min
    TYPE_SUMMARY: 0,
    TYPE_RATE_LIMITED: 120,
}


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------


def _format_message(
    msg_type: str,
    video_id: str,
    stage: str,
    milestone: str,
    *,
    progress_done: int = 0,
    progress_total: int = 0,
    next_action: str = "",
    details: list[str] | None = None,
    wait_minutes: int = 0,
) -> str:
    """Format a notification message using the standard template."""
    emoji = _EMOJI.get(msg_type, "\u2139\uFE0F")
    label = _type_label(msg_type)

    # Header line
    prefix = "[Rayviews Lab]"
    if milestone:
        header = f"{prefix} {emoji} {video_id} — {label} / {milestone}"
    else:
        header = f"{prefix} {emoji} {video_id} — {label}"

    if stage:
        header = f"{prefix} {emoji} {video_id} — {stage.title()} / {milestone or label}"

    lines = [header]

    # Progress
    if progress_total > 0:
        lines.append(f"Progress: {progress_done}/{progress_total}")

    # Wait time (rate limit)
    if wait_minutes > 0:
        lines.append(f"Waiting: {wait_minutes} minutes, will retry automatically")

    # Next action (mandatory for non-heartbeat)
    if next_action:
        lines.append(f"Next: {next_action}")
    elif msg_type != TYPE_HEARTBEAT:
        # Auto-suggest from pipeline status
        status = get_status(video_id)
        suggestion = _suggest_next_action(status)
        if suggestion:
            lines.append(f"Next: {suggestion}")

    # Details (max 3 bullets)
    if details:
        lines.append("Details:")
        for detail in details[:3]:
            lines.append(f"- {detail}")

    return "\n".join(lines)


def _type_label(msg_type: str) -> str:
    labels = {
        TYPE_START: "Pipeline started",
        TYPE_PROGRESS: "Milestone complete",
        TYPE_ACTION_REQUIRED: "ACTION REQUIRED",
        TYPE_ERROR: "ERROR",
        TYPE_HEARTBEAT: "Running",
        TYPE_SUMMARY: "Pipeline complete",
        TYPE_RATE_LIMITED: "Rate limited",
    }
    return labels.get(msg_type, msg_type)


# ---------------------------------------------------------------------------
# Anti-spam
# ---------------------------------------------------------------------------


def _dedup_key(msg_type: str, video_id: str, stage: str, milestone: str) -> str:
    return f"{msg_type}:{video_id}:{stage}:{milestone}"


def _should_send(video_id: str, dedup_key: str, msg_type: str) -> bool:
    """Check anti-spam rules. Returns True if OK to send."""
    status = get_status(video_id)

    # Never send exact same message twice in a row
    if status.last_notify_key == dedup_key:
        return False

    # Throttle by type
    throttle = _THROTTLE_SECONDS.get(msg_type, 30)
    if throttle > 0:
        elapsed = time.time() - status.last_notify_at
        if elapsed < throttle:
            return False

    return True


# ---------------------------------------------------------------------------
# Public API — send notifications
# ---------------------------------------------------------------------------


def notify_start(video_id: str, *, details: list[str] | None = None) -> bool:
    """Pipeline started for video_id."""
    key = _dedup_key(TYPE_START, video_id, "", "")
    if not _should_send(video_id, key, TYPE_START):
        return False

    msg = _format_message(
        TYPE_START, video_id, "", "",
        next_action="Pipeline running. No action required.",
        details=details,
    )
    ok = send_telegram(msg)
    if ok:
        mark_notified(video_id, key)
    return ok


def notify_progress(
    video_id: str,
    stage: str,
    milestone: str,
    *,
    progress_done: int = 0,
    progress_total: int = 0,
    next_action: str = "",
    details: list[str] | None = None,
) -> bool:
    """Milestone completed. Only sends on actual milestones, not every step."""
    key = _dedup_key(TYPE_PROGRESS, video_id, stage, milestone)
    if not _should_send(video_id, key, TYPE_PROGRESS):
        return False

    msg = _format_message(
        TYPE_PROGRESS, video_id, stage, milestone,
        progress_done=progress_done,
        progress_total=progress_total,
        next_action=next_action,
        details=details,
    )
    ok = send_telegram(msg)
    if ok:
        mark_notified(video_id, key)
    return ok


def notify_action_required(
    video_id: str,
    stage: str,
    issue: str,
    *,
    next_action: str = "",
) -> bool:
    """Human intervention needed (login, captcha, missing config, etc.)."""
    key = _dedup_key(TYPE_ACTION_REQUIRED, video_id, stage, issue)
    if not _should_send(video_id, key, TYPE_ACTION_REQUIRED):
        return False

    msg = _format_message(
        TYPE_ACTION_REQUIRED, video_id, stage, issue,
        next_action=next_action or f"Resolve: {issue}",
    )
    ok = send_telegram(msg)
    if ok:
        mark_notified(video_id, key)
    return ok


def notify_error(
    video_id: str,
    stage: str,
    milestone: str,
    error: str,
    *,
    next_action: str = "",
    details: list[str] | None = None,
) -> bool:
    """Step failed after retries."""
    key = _dedup_key(TYPE_ERROR, video_id, stage, milestone)
    if not _should_send(video_id, key, TYPE_ERROR):
        return False

    msg = _format_message(
        TYPE_ERROR, video_id, stage, milestone,
        next_action=next_action or f"Investigate and retry: {milestone}",
        details=details or [f"Reason: {error[:100]}"],
    )
    ok = send_telegram(msg)
    if ok:
        mark_notified(video_id, key)
    return ok


def notify_heartbeat(
    video_id: str,
    stage: str = "",
    milestone: str = "",
    *,
    progress_done: int = 0,
    progress_total: int = 0,
) -> bool:
    """Lightweight 'still running' ping. Only sends if threshold met."""
    if not should_heartbeat(video_id):
        return False

    key = _dedup_key(TYPE_HEARTBEAT, video_id, stage, milestone)
    if not _should_send(video_id, key, TYPE_HEARTBEAT):
        return False

    status = get_status(video_id)
    s = stage or status.stage
    m = milestone or status.milestone
    pd = progress_done or status.progress_done
    pt = progress_total or status.progress_total

    msg = _format_message(
        TYPE_HEARTBEAT, video_id, s, m,
        progress_done=pd,
        progress_total=pt,
        next_action="No action required",
    )
    ok = send_telegram(msg)
    if ok:
        mark_notified(video_id, key)
    return ok


def notify_rate_limited(
    video_id: str,
    stage: str,
    wait_minutes: int,
) -> bool:
    """Model/API rate-limited. NOT a fatal error."""
    key = _dedup_key(TYPE_RATE_LIMITED, video_id, stage, "")
    if not _should_send(video_id, key, TYPE_RATE_LIMITED):
        return False

    msg = _format_message(
        TYPE_RATE_LIMITED, video_id, stage, "Rate limited",
        wait_minutes=wait_minutes,
        next_action=f"Waiting {wait_minutes} minutes, will retry automatically",
    )
    ok = send_telegram(msg)
    if ok:
        mark_notified(video_id, key)
    return ok


def notify_summary(
    video_id: str,
    *,
    details: list[str] | None = None,
    next_action: str = "Review outputs and upload to YouTube",
) -> bool:
    """Pipeline complete summary."""
    key = _dedup_key(TYPE_SUMMARY, video_id, "", "")

    msg = _format_message(
        TYPE_SUMMARY, video_id, "", "All stages complete",
        next_action=next_action,
        details=details,
    )
    ok = send_telegram(msg)
    if ok:
        mark_notified(video_id, key)
    return ok
